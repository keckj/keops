"""
=========
Multi GPU
=========

On multi-device clusters,
let's see how to select the card on which a KeOps
operation will be performed.

"""

###############################################################
# Setup
# -------------
# Standard imports:

import numpy as np
import torch
import matplotlib.pyplot as plt

from pykeops.numpy import Genred
from pykeops.numpy.utils import IsGpuAvailable

###############################################################
# Define the list of gpu ids to be tested:

# By default we assume that there are two GPUs available with 0 and 1 labels:
gpuids = [0,1] if torch.cuda.device_count() > 1 else [0]


###############################################################
# KeOps Kernel
# -------------
# Define some arbitrary KeOps routine:

formula   =  'Square(p-a) * Exp(x+y)'
variables = ['x = Vx(3)','y = Vy(3)','a = Vy(1)','p = Pm(1)']

type = 'float32'  # May be 'float32' or 'float64'

my_routine = Genred(formula, variables, reduction_op='Sum', axis=1, cuda_type=type)


###############################################################
#  Generate some data, stored on the CPU (host) memory:
#

M = 1000
N = 2000
x = np.random.randn(M,3).astype(type)
y = np.random.randn(N,3).astype(type)
a = np.random.randn(N,1).astype(type)
p = np.random.randn(1,1).astype(type)

#########################################
# Launch our routine on the CPU:
#

c = my_routine(x, y, a, p, backend='CPU')

#########################################
# And on our GPUs, with copies between 
# the Host and Device memories:
#
if IsGpuAvailable():
    for gpuid in gpuids:
        d = my_routine(x, y, a, p, backend='GPU', device_id=gpuid)
        print('Relative error on gpu {}: {:1.3e}'.format( gpuid, 
                float( np.sum(np.abs(c - d)) / np.sum(np.abs(c)) ) ))
    
        # Plot the results next to each other:
        for i in range(3):
            plt.subplot(3, 1, i+1)
            plt.plot(c[:40,i],  '-', label='keops')
            plt.plot(d[:40,i], '--', label='GPU {}'.format(gpuid))
            plt.legend(loc='lower right')

        plt.tight_layout() ; plt.show()

