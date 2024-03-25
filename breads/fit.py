import numpy as np
from scipy.optimize import lsq_linear
from scipy.special import loggamma
import matplotlib.pyplot as plt
import warnings
from copy import copy

__all__ =  ('fitfm', 'log_prob', 'combined_log_prob', 'nlog_prob')

def fitfm(nonlin_paras, dataobj, fm_func, fm_paras,computeH0 = True,bounds = None,
          residuals=None,residuals_H0=None,noise4residuals=None):
    """
    Fit a forard model to data returning probabilities and best fit linear parameters.

    Args:
        nonlin_paras: [p1,p2,...] List of non-linear parameters such as rv, y, x. The meaning and number of non-linear
            parameters depends on the forward model defined.
        dataobj: A data object of type breads.instruments.instrument.Instrument to be analyzed.
        fm_func: A forward model function. See breads.fm.template.template() for an example.
        fm_paras: Additional parameters for fm_func (other than non-linear parameters and dataobj)
        computeH0: If true (default), compute the probability of the model removing the first element of the linear
            model; See second ouput log_prob_H0. This can be used to compute the Bayes factor for a fixed set of
            non-linear parameters
        bounds: (/!\ Caution: the calculation of log prob is only theoretically accurate if no bounds are used.)
            Bounds on the linear parameters used in lsq_linear as a tuple of arrays (min_vals, maxvals).
            e.g. ([0,0,...], [np.inf,np.inf,...]) default no bounds.
            Each numpy array must have shape (N_linear_parameters,).


    Returns:
        log_prob: Probability of the model marginalized over linear parameters.
        log_prob_H0: Probability of the model without the planet marginalized over linear parameters.
        rchi2: noise scaling factor
        linparas: Best fit linear parameters
        linparas_err: Uncertainties of best fit linear parameters
    """
    fm_out = fm_func(nonlin_paras,dataobj,**fm_paras)

    if len(fm_out) == 3:
        d, M, s = fm_out
    if len(fm_out) == 4:
        d, M, s,extra_outputs = fm_out

    N_linpara = M.shape[1]
    N_data = np.size(d)
    linparas = np.ones(N_linpara)+np.nan
    linparas_err = np.ones(N_linpara)+np.nan
    if N_data == 0:
        log_prob = -np.inf
        log_prob_H0 = -np.inf
        rchi2 = np.inf
        return log_prob, log_prob_H0, rchi2, linparas, linparas_err

    if N_linpara == 1:
        computeH0 = False

    if bounds is None:
        _bounds = ([-np.inf,]*N_linpara,[np.inf,]*N_linpara)
    else:
        _bounds = (copy(bounds[0]),copy(bounds[1]))

    validpara = np.where(np.nanmax(np.abs(M),axis=0)!=0)
    _bounds = (np.array(_bounds[0])[validpara[0]],np.array(_bounds[1])[validpara[0]])
    M = M[:,validpara[0]]

    d = d / s
    M = M / s[:, None]

    if len(fm_out) == 4:
        if "regularization" in extra_outputs.keys():
            d_reg,s_reg = extra_outputs["regularization"]
            s_reg = s_reg[validpara]
            d_reg = d_reg[validpara]
            where_reg = np.where(np.isfinite(s_reg))
            s_reg = s_reg[where_reg]
            d_reg = d_reg[where_reg]
            M_reg = np.zeros((np.size(where_reg[0]),M.shape[1]))
            M_reg[np.arange(np.size(where_reg[0])),where_reg[0]] = 1/s_reg
            M = np.concatenate([M,M_reg],axis=0)
            d = np.concatenate([d,d_reg/s_reg])
            s = np.concatenate([s,s_reg])


    if 0 not in validpara[0]:
        log_prob = -np.inf
        log_prob_H0 = -np.inf
        rchi2 = np.inf
        return log_prob, log_prob_H0, rchi2, linparas, linparas_err
    else:
        logdet_Sigma = np.sum(2 * np.log(s))
        paras = lsq_linear(M, d,bounds=_bounds).x
        # paras = lsq_linear(M, d).x

        m = np.dot(M, paras)
        r = d  - m
        chi2 = np.nansum(r**2)
        # rchi2 = chi2 / np.size(r)
        rchi2 = np.nansum(r[0:N_data]**2) / N_data

        if residuals is not None:
            residuals[0:np.size(s)] = r
        if noise4residuals is not None:
            noise4residuals[0:np.size(s)] = s
        # plt.figure()
        # for col in M.T:
        #     plt.plot(col / np.nanmean(col))
        # plt.show()

        MTM = np.dot(M.T, M)
        try:
            covphi = rchi2 * np.linalg.inv(MTM)
            # covphi = np.linalg.inv(MTM)
            slogdet_icovphi0 = np.linalg.slogdet(MTM)
        except:
            log_prob = -np.inf
            log_prob_H0 = -np.inf
            rchi2 = np.inf
            return log_prob, log_prob_H0, rchi2, linparas, linparas_err

        # print("log_prob",logdet_Sigma,slogdet_icovphi0[1],(N_data - N_linpara + 2 - 1),chi2)
        # print("slogdet_icovphi0",slogdet_icovphi0)
        log_prob = -0.5 * logdet_Sigma - 0.5 * slogdet_icovphi0[1] - (N_data - M.shape[1] + 2 - 1) / 2 * np.log(chi2) + \
                    loggamma((N_data - M.shape[1] + 2 - 1) / 2) + (M.shape[1] - N_data) / 2 * np.log(2 * np.pi)
        diagcovphi = copy(np.diag(covphi))
        diagcovphi[np.where(diagcovphi<0.0)] = np.nan
        paras_err = np.sqrt(diagcovphi)

        if computeH0:
            paras_H0 = lsq_linear(M[:,1::], d,bounds=(np.array(_bounds[0])[1::],np.array(_bounds[1])[1::])).x
            # paras_H0 = lsq_linear(M[:,1::], d).x
            m_H0 = np.dot(M[:,1::] , paras_H0)
            r_H0 = d  - m_H0
            chi2_H0 = np.nansum(r_H0**2)
            slogdet_icovphi0_H0 = np.linalg.slogdet(np.dot(M[:,1::].T, M[:,1::]))
            #todo check the maths when N_linpara is different from M.shape[1]. E.g. at the edge of the FOV
            # log_prob_H0 = -0.5*logdet_Sigma - 0.5*slogdet_icovphi0_H0[1] - (N_data-1+N_linpara-1-1)/2*np.log(chi2_H0)+ \
            #               loggamma((N_data-1+(N_linpara-1)-1)/2)+((N_linpara-1)-N_data)/2*np.log(2*np.pi)
            log_prob_H0 = -0.5*logdet_Sigma - 0.5*slogdet_icovphi0_H0[1] - (N_data+(M.shape[1]-1)+2-1)/2*np.log(chi2_H0)+ \
                          loggamma((N_data-(M.shape[1]-1)+2-1)/2)+((M.shape[1]-1)-N_data)/2*np.log(2*np.pi)
            if residuals_H0 is not None:
                residuals_H0[0:np.size(s)] = r_H0
        else:
            log_prob_H0 = np.nan

        linparas[validpara] = paras
        linparas_err[validpara] = paras_err

        # import matplotlib.pyplot as plt
        # print(log_prob, log_prob_H0, rchi2)
        # print(linparas)
        # print(linparas_err)
        # plt.plot(d,label="d")
        # plt.plot(m,label="m")
        # plt.plot(r,label="r")
        # plt.legend()
        # plt.show()


        return log_prob, log_prob_H0, rchi2, linparas, linparas_err

def log_prob(nonlin_paras, dataobj, fm_func, fm_paras,nonlin_lnprior_func=None,bounds=None):
    """
    Wrapper to fit_fm() but only returns the log probability marginalized over the linear parameters.

    Args:
        nonlin_paras: [p1,p2,...] List of non-linear parameters such as rv, y, x. The meaning and number of non-linear
            parameters depends on the forward model defined.
        dataobj: A data object of type breads.instruments.instrument.Instrument to be analyzed.
        fm_func: A forward model function. See breads.fm.template.template() for an example.
        fm_paras: Additional parameters for fm_func (other than non-linear parameters and dataobj)
        computeH0: If true (default), compute the probability of the model removing the first element of the linear
            model; See second ouput log_prob_H0. This can be used to compute the Bayes factor for a fixed set of
            non-linear parameters
        bounds: (/!\ Caution: the calculation of log prob is only theoretically accurate if no bounds are used.)
            Bounds on the linear parameters used in lsq_linear as a tuple of arrays (min_vals, maxvals).
            e.g. ([0,0,...], [np.inf,np.inf,...]). default no bounds.
            Each numpy array must have shape (N_linear_parameters,).

    Returns:
        log_prob: Probability of the model marginalized over linear parameters.
    """
    if nonlin_lnprior_func is not None:
        prior = nonlin_lnprior_func(nonlin_paras)
    else:
        prior = 0
    try:
        lnprob = fitfm(nonlin_paras, dataobj, fm_func, fm_paras,computeH0=False,bounds=bounds)[0]+prior
    except:
        lnprob =  -np.inf
    return lnprob


def combined_log_prob(nonlin_paras, dataobjlist,fm_funclist, fm_paraslist, nonlin_lnprior_func=None,bounds=None):
    '''
    For use when you have multiple data objects and want to combine the log-likelihoods for MCMC sampling

    Args:
        nonlin_paras: [p1,p2,...] List of non-linear parameters such as rv, y, x. The meaning and number of non-linear
            parameters depends on the forward model defined.
        dataobjlist: A list of data objects to combine
        fm_funclist: A list of fm_func for each data object
        fm_paraslist: A list of fm_paras to use as arguments for it's respective fm_func
        nonlin_lnprior_func: A function to compute priors, if None, defaults to zero priors
    '''
    combined_lnprob = 0
    for i, dataobj in enumerate(dataobjlist):
        lnprob=log_prob(nonlin_paras = nonlin_paras, dataobj=dataobj, fm_func=fm_funclist[i], fm_paras= fm_paraslist[i],nonlin_lnprior_func=None,bounds=None)
        combined_lnprob += lnprob
    return combined_lnprob

def nlog_prob(nonlin_paras, dataobj, fm_func, fm_paras,nonlin_lnprior_func=None,bounds=None):
    """
   Returns the negative of the log_prob() for minimization routines.

    Args:
        nonlin_paras: [p1,p2,...] List of non-linear parameters such as rv, y, x. The meaning and number of non-linear
            parameters depends on the forward model defined.
        dataobj: A data object of type breads.instruments.instrument.Instrument to be analyzed.
        fm_func: A forward model function. See breads.fm.template.template() for an example.
        fm_paras: Additional parameters for fm_func (other than non-linear parameters and dataobj)
        computeH0: If true (default), compute the probability of the model removing the first element of the linear
            model; See second ouput log_prob_H0. This can be used to compute the Bayes factor for a fixed set of
            non-linear parameters
        bounds: (/!\ Caution: the calculation of log prob is only theoretically accurate if no bounds are used.)
            Bounds on the linear parameters used in lsq_linear as a tuple of arrays (min_vals, maxvals).
            e.g. ([0,0,...], [np.inf,np.inf,...]) default no bounds.
            Each numpy array must have shape (N_linear_parameters,).

    Returns:
        log_prob: Probability of the model marginalized over linear parameters.
    """
    nlogprob_val =  - log_prob(nonlin_paras, dataobj, fm_func, fm_paras,nonlin_lnprior_func,bounds)
    # print( nlogprob_val, nonlin_paras)
    return nlogprob_val