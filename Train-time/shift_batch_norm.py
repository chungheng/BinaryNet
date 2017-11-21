# -*- coding: utf-8 -*-

"""
Preliminary implementation of shift-based batch normalization for Lasagne.
validation.

Author: Chung-Heng Yeh
"""

import numpy as np
import lasagne
import theano
import theano.tensor as T

class BatchNormSfhitPow2Layer(lasagne.layers.Layer):

    def __init__(self, incoming, axes=None, epsilon=1e-5, alpha=0.125,
            nonlinearity=None, **kwargs):
        """
        Instantiates a layer performing batch normalization of its inputs,
        following Ioffe et al. (http://arxiv.org/abs/1502.03167).

        @param incoming: `Layer` instance or expected input shape
        @param axes: int or tuple of int denoting the axes to normalize over;
            defaults to all axes except for the second if omitted (this will
            do the correct thing for dense layers and convolutional layers)
        @param epsilon: small constant added to the standard deviation before
            dividing by it, to avoid numeric problems
        @param alpha: coefficient for the exponential moving average of
            batch-wise means and standard deviations computed during training;
            the larger, the more it will depend on the last batches seen
        @param nonlinearity: nonlinearity to apply to the output (optional)
        """
        super(BatchNormSfhitPow2Layer, self).__init__(incoming, **kwargs)
        if axes is None:
            # default: normalize over all but the second axis
            axes = (0,) + tuple(range(2, len(self.input_shape)))
        elif isinstance(axes, int):
            axes = (axes,)
        self.axes = axes
        self.epsilon = epsilon
        self.alpha = alpha
        if nonlinearity is None:
            nonlinearity = lasagne.nonlinearities.identity
        self.nonlinearity = nonlinearity
        shape = list(self.input_shape)
        broadcast = [False] * len(shape)
        for axis in self.axes:
            shape[axis] = 1
            broadcast[axis] = True
        if any(size is None for size in shape):
            raise ValueError("BatchNormLayer needs specified input sizes for "
                             "all dimensions/axes not normalized over.")
        dtype = theano.config.floatX
        self.centered = self.add_param(lasagne.init.Constant(0), shape,
                        'centered', trainable=False, regularizable=False)
        self.mean = self.add_param(lasagne.init.Constant(0), shape, 'mean',
                                   trainable=False, regularizable=False)
        self.std = self.add_param(lasagne.init.Constant(1), shape, 'std',
                                  trainable=False, regularizable=False)
        # self.beta = self.add_param(lasagne.init.Constant(0), shape, 'beta',
        #                            trainable=True, regularizable=True)
        # self.gamma = self.add_param(lasagne.init.Constant(1), shape, 'gamma',
        #                             trainable=True, regularizable=False)

    def get_output_for(self, input, deterministic=False, **kwargs):
        if deterministic:
            # use stored mean and std
            mean = self.mean
            std = self.std
        else:
            # use this batch's mean and std
            mean = input.mean(self.axes, keepdims=True)
            # and update the stored mean and std:
            # we create (memory-aliased) clones of the stored mean and std
            running_mean = theano.clone(self.mean, share_inputs=False)
            running_mean.default_update = ((1 - self.alpha) * running_mean +
                                           self.alpha * mean)

            centered = input - mean

            # prevent T.log2 results in NaN
            centered_log2 = T.log2(T.abs_(centered))
            centered_log2 = T.switch(T.eq(centered, 0.), 0., centered_log2)

            centered_ap2 = T.pow(2., T.round(centered_log2))
            std = T.mean(T.abs_(centered)*centered_ap2,
                         self.axes, keepdims=True)
            std = T.inv(T.sqrt(std+self.epsilon))

            running_std = theano.clone(self.std, share_inputs=False)
            # set a default update for them

            running_std.default_update = ((1 - self.alpha) * running_std +
                                          self.alpha * std)
            # and include them in the graph so their default updates will be
            # applied (although the expressions will be optimized away later)

            std = T.pow(2., T.round(T.log2(std)))
            mean += 0 * running_mean
            std += 0 * running_std

        mean = T.addbroadcast(mean, *self.axes)
        std = T.addbroadcast(std, *self.axes)

        normalized = (input - mean) * std
        return self.nonlinearity(normalized)

def batch_norm_pow_2(layer):
    """
    Convenience function to apply batch normalization to a given layer's output.
    Will steal the layer's nonlinearity if there is one (effectively introducing
    the normalization right before the nonlinearity), and will remove the
    layer's bias if there is one (because it would be redundant).

    @param layer: The `Layer` instance to apply the normalization to; note that
        it will be irreversibly modified as specified above
    @return: A `BatchNormSfhitPow2Layer` instance stacked on the given `layer`
    """
    nonlinearity = getattr(layer, 'nonlinearity', None)
    if nonlinearity is not None:
        layer.nonlinearity = lasagne.nonlinearities.identity
    if hasattr(layer, 'b'):
        del layer.params[layer.b]
        layer.b = None
    return BatchNormSfhitPow2Layer(layer, nonlinearity=nonlinearity)
