from numba import jit, f8, int8, void
import numpy as np


def interp_knots(_X, _Y, trials, xtst):
    """

    Parameters
    ----------
    X : x coordinates of knots for each trial (shape: trials x n_knots)
    Y : y coordinates of knots for each trial (shape: trials x n_knots)
    xtst : queried x coordinate for each trial (shape: trials)

    Note:
        X is assumed to be sorted along axis=1

    Returns
    -------
    ytst : interpolated y value for each x in xtst (shape: trials)
    """

    X = _X[trials]
    Y = _Y[trials]

    # allocate result
    ytst = np.empty_like(xtst)

    # for each trial (row of X) find first knot larger than test point
    p = np.argmin(xtst[:, None] > X, axis=1)

    # make sure that we never try to interpolate to the left of
    # X[:,0] to avoid out-of-bounds error. Test points requiring
    # extrapolation are clipped (see below).
    np.maximum(1, p, out=p)

    # indexing vector along trials (used to index with p)
    k = np.arange(len(p))

    # distance between adjacent knots
    dx = np.diff(_X, axis=1)[trials]

    # fractional distance of test points between knots
    lam = (xtst - X[k, p-1]) / dx[k, p-1]

    # linear interpolation
    ytst = (Y[k, p-1]*(1-lam)) + (Y[k, p]*(lam))

    # clip test values below X[:, 0] or above X[:, -1]
    idx = lam > 1
    ytst[idx] = Y[idx, -1]
    idx = lam < 0
    ytst[idx] = Y[idx, 0]

    return ytst


# @jit(void(f8[:], f8[:, :], f8[:, :], f8[:, :], f8[:, :], f8[:], f8[:], int8[:, :, :]), nopython=True)
@jit(nopython=True)
def bcast_interp(xtst, X, Y, warps, template, new_loss, last_loss, data):

    T = len(xtst)
    N = len(X[0])
    n_neurons = data.shape[2]

    for i in range(len(X)):

        # do interpolation
        y0 = Y[i, 0]
        x0 = X[i, 0]
        slope = (Y[i, 1] - Y[i, 0]) / (X[i, 1] - X[i, 0])

        m = 0
        n = 1

        new_loss[i] = 0
        thres = last_loss[i]**2

        while (m < T) and (new_loss[i] < thres):

            # update interpolation point
            while (n < N-1) and (m/(T-1) > X[i, n]):
                y0 = Y[i, n]
                x0 = X[i, n]
                slope = (Y[i, n+1] - y0) / (X[i, n+1] - x0)
                n += 1

            # do interpolation and move on to next element in xtst
            z = y0 + slope*(xtst[m] - x0)

            # clip warp interpolation between zero and one
            if z < 0:
                warps[i, m] = 0.0

                # evaluate loss at first index
                for neu in range(n_neurons):
                    new_loss[i] += (template[0, neu] - data[i, m, neu]) ** 2

            elif z > 1:
                warps[i, m] = 1.0

                # evaluate loss at last index
                for neu in range(n_neurons):
                    new_loss[i] += (template[-1, neu] - data[i, m, neu]) ** 2

            else:
                warps[i, m] = z
                _i = z * (T-1)
                rem = _i % 1
                idx = int(_i)

                # evaluate loss at interpolant
                for neu in range(n_neurons):
                    new_loss[i] += (
                        (1 - rem) * template[idx, neu] +
                        rem * template[idx + 1, neu] -
                        data[i, m, neu]
                    ) ** 2

            # move to next timepoint
            m += 1

        new_loss[i] = new_loss[i] ** 0.5
