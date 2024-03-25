import multiprocessing as mp
import numpy as np
import itertools

from scipy.optimize import lsq_linear
from scipy.special import loggamma
from scipy.interpolate import InterpolatedUnivariateSpline
from astropy import constants as const

from breads.fit import fitfm

__all__ = ('grid_search', 'process_chunk')

try:
    import mkl
    mkl_exists = True
except ImportError:
    mkl_exists = False



def process_chunk(args):
    """
    Process for grid_search()
    """
    nonlin_paras_list, dataobj, fm_func, fm_paras, bounds,computeH0 = args

    for k, nonlin_paras in enumerate(zip(*nonlin_paras_list)):
        try:
        # if 1:
            log_prob,log_prob_H0,rchi2,linparas,linparas_err = fitfm(nonlin_paras,dataobj,fm_func,fm_paras,bounds=bounds,computeH0=computeH0)
            N_linpara = np.size(linparas)
            if k == 0:
                out_chunk = np.zeros((np.size(nonlin_paras_list[0]),1+1+1+2*N_linpara))+np.nan
            out_chunk[k,0] = log_prob
            out_chunk[k,1] = log_prob_H0
            out_chunk[k,2] = rchi2
            out_chunk[k,3:(N_linpara+3)] = linparas
            out_chunk[k,(N_linpara+3):(2*N_linpara+3)] = linparas_err
        except Exception as e:
            print(nonlin_paras,e)
    try:
    # if 1:
        return out_chunk
    except Exception as e:
        print(nonlin_paras,e)
        return None


def grid_search(para_vecs,dataobj,fm_func,fm_paras,tuple_flag=False,numthreads=None,bounds=None,computeH0=False):
    """
    Planet detection, CCF, or grid search routine.
    It fits for the non linear parameters of a forward model over a user-specified grid of values while marginalizing
    over the linear parameters. For a planet detection or CCF routine, choose a forward model (fm_func) and provide a
    grid of x,y, and RV values.

    SNR (detection maps or CCFs) can be computed as:
    N_linpara = (out.shape[-1]-2)//2
    snr = out[...,3]/out[...,3+N_linpara]

    The natural logarithm of the Bayes factor can be computed as
    bayes_factor = out[...,0] - out[...,1]

    Args:
        para_vecs: [vec1,vec2,...] List of 1d arrays defining the sampling of the grid of non-linear parameters such as
            rv, y, x. The meaning and number of non-linear parameters depends on the forward model defined.
        dataobj: A data object of type breads.instruments.instrument.Instrument to be analyzed.
        fm_func: A forward model function. See breads.fm.template.template() for an example.
        fm_paras: Additional parameters for fm_func (other than non-linear parameters and dataobj)
        numthreads: Number of processes to be used in parallelization. Non parallization if defined as None (default).
        bounds: (/!\ Caution: the calculation of log prob is only theoretically accurate if no bounds are used.)
            Bounds on the linear parameters used in lsq_linear as a tuple of arrays (min_vals, maxvals).
            e.g. ([0,0,...], [np.inf,np.inf,...]). default no bounds.
            Each numpy array must have shape (N_linear_parameters,).
            
        tuple_flag: True if para_vecs is a list of tuples defining the sampling of the "nongrid" inputs of non-linear parameters

    Returns:
        log_prob: Probability of the model marginalized over linear parameters.
        log_prob_H0: Probability of the model without the planet marginalized over linear parameters.
        rchi2: noise scaling factor
        linparas: Best fit linear parameters
        linparas_err: Uncertainties of best fit linear parameters

    """
    if tuple_flag:
        tuple_array = np.array(para_vecs)
        para_grids = [tuple_array[:,i] for i in range(tuple_array.shape[-1])]
    else:
        para_grids = [np.ravel(pgrid) for pgrid in np.meshgrid(*para_vecs,indexing="ij")]

    if numthreads is None:
        _out = process_chunk((para_grids,dataobj,fm_func,fm_paras,bounds,computeH0))
        if tuple_flag:
            out_shape = [len(para_vecs)]+[_out.shape[-1],]
        else:
            out_shape = [np.size(v) for v in para_vecs]+[_out.shape[-1],]
        out = np.reshape(_out,out_shape)
    else:
        mypool = mp.Pool(processes=numthreads)
        chunk_size = np.max([1,np.size(para_grids[0])//(3*numthreads)])
        N_chunks = np.size(para_grids[0])//chunk_size
        nonlin_paras_lists = []
        indices_lists = []
        for k in range(N_chunks-1):
            nonlin_paras_lists.append([pgrid[(k*chunk_size):((k+1)*chunk_size)] for pgrid in para_grids])
            indices_lists.append(np.arange((k*chunk_size),((k+1)*chunk_size)))
        nonlin_paras_lists.append([pgrid[((N_chunks-1)*chunk_size):np.size(para_grids[0])] for pgrid in para_grids])
        indices_lists.append(np.arange(((N_chunks-1)*chunk_size),np.size(para_grids[0])))

        output_lists = mypool.map(process_chunk, zip(nonlin_paras_lists,
                                                     itertools.repeat(dataobj),
                                                     itertools.repeat(fm_func),
                                                     itertools.repeat(fm_paras),
                                                     itertools.repeat(bounds),
                                                     itertools.repeat(computeH0)))

        outarr_not_created = True
        for k,(indices, output_list) in enumerate(zip(indices_lists,output_lists)):
            if output_list is None:
                continue
            if outarr_not_created:
                if tuple_flag:
                    out_shape = [len(para_vecs)]+[np.size(output_list[0]),]
                else:
                    out_shape = [np.size(v) for v in para_vecs]+[np.size(output_list[0]),]
                out = np.zeros(out_shape)
                outarr_not_created = False
            for l,outvec in zip(indices,output_list):
                #print('l: {}'.format(l))
                #print('outvec: {}'.format(outvec))
                #print('outvec.shape: {}'.format(outvec.shape))
                if tuple_flag:
                    out[l,:] = outvec
                else:
                    out[np.unravel_index(l,out_shape[0:len(para_vecs)])] = outvec

        mypool.close()
        mypool.join()

    N_linpara = int((out.shape[-1]-3)/2)
    out = np.moveaxis(out, -1, 0)
    log_prob = out[0]
    log_prob_H0 = out[1]
    rchi2 = out[2]
    linparas = np.moveaxis(out[3:3+N_linpara], 0, -1)
    linparas_err = np.moveaxis(out[3+N_linpara:3+2*N_linpara], 0, -1)

    return log_prob,log_prob_H0,rchi2,linparas,linparas_err
