import os.path
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)) + os.path.sep + '..')

from cudaconv import cuda_conv_generic
import torch
import numpy
from torch.autograd import Variable

# Computation are made in float32
dtype = torch.FloatTensor 

# See github.com/pytorch/pytorch/pull/1016 , pytorch.org/docs/0.2.0/notes/extending.html
# for reference on the forward-backward syntax
class GenericKernelProduct(torch.autograd.Function):
	""" 
	Computes a Generic Kernel Product specified by a formula (string) such as :
	formula = "Scal< Square<Scalprod<U,V>>, Scal< Exp< Scal<Constant<C>, Minus<SqNorm2<Subtract<X,Y>>> > >,  B> >"
	"""
	
	@staticmethod
	def forward(ctx, aliases, formula, signature, sum_index, *args):
		""" 
		Computes a Generic Kernel Product specified by a formula (string) such as :
		```
		formula = "Scal< Square<Scalprod<U,V>>, Scal< Exp< Scal<Constant<C>, Minus<SqNorm2<Subtract<X,Y>>> > >,  B> >"
		```
		i.e.       <U,V>^2 * exp(-C*|X-Y|^2 ) * B 
		
		aliases is a list of strings, which specifies "who is who"; for example :
		```
		aliases = [ "DIMPOINT = 3", "DIMVECT = 4", "DIMOUT = 5",
					"C = Param<0>"          ,   # 1st parameter
					"X = Var<0,DIMPOINT,0>" ,   # 1st variable, dim 3, indexed by i
					"Y = Var<1,DIMPOINT,1>" ,   # 2nd variable, dim 3, indexed by j
					"U = Var<2,DIMVECT ,0>" ,   # 3rd variable, dim 4, indexed by i
					"V = Var<3,DIMVECT ,1>" ,   # 4th variable, dim 4, indexed by j
					"B = Var<4,DIMOUT  ,1>" ]   # 5th variable, dim 5, indexed by j
		```
		
		signature is a list of (DIM, CAT) integer pairs allowing the user to specify
		the respective dimensions of the output (head) and variables (tail of the list).
		Remember that CAT=0 for "x_i" indexing  variables,
		              CAT=1 for "y_j" summation variables,
		              CAT=2 for parameters.
		For instance,
		```
		signature = [ (5,0), (1,2), (3,0), (3,1), (4,0), (4,1), (5,1) ]
		# stands for:  R_i ,   C  ,  X_i  , Y_j  , U_i  , V_j  , B_j   .
		```
		
		Theoretically, signature could be inferred from formula+aliases...
		But asking the user to provide it explicitely is a good way to let him double-check
		his formula, and makes debugging easier.
		
		With the values defined above,
		```
		genconv = GenericKernelProduct().apply
		R = genconv( aliases, formula, signature, C, X, Y, U, V, B )
		```
		is a legal call, where :
		- C is a scalar              (torch Variable)
		- X is a nx-by-3 float array (torch Variable)
		- Y is a ny-by-3 float array (torch Variable)
		- U is a nx-by-4 float array (torch Variable)
		- V is a ny-by-4 float array (torch Variable)
		- B is a ny-by-5 float array (torch Variable)
		which outputs:
		- R, an  nx-by-5 float array (torch Variable)
		
		(nx and ny are automatically inferred from the data; 
		an error is thrown if the lengths of the input arrays are not compatible with each other)
		
		Eventually, in this example, we've computed a "Gaussian-CauchyBinet varifold kernel"
		with a signal B of dimension 4 :
		
		R_i = \sum_j <U_i,V_j>^2 * exp(-C*|X_i-Y_j|^2 ) * B_j
		
		Its derivatives wrt. X, Y, U, V, B are automatically computed (symbolically, without backprop), 
		and are accessible using standard PyTorch syntax.
		
		N.B.: The data type (float v. double) is inferred automatically from the PyTorch type of args.
			  The CPU/GPU mode is chosen automatically.
			  The grid_scheme  (1D v. 2D) is chosen according to heuristic rules.
		"""
		# Save everything to compute the gradient -----------------------------------------------
		# N.B.: relying on the "ctx.saved_variables" attribute is necessary
		#       if you want to be able to differentiate the output of the backward
		#       once again. It helps pytorch to keep track of "who is who".
		ctx.save_for_backward( *args ) # Call at most once in the "forward".
		ctx.aliases   = aliases
		ctx.formula   = formula
		ctx.signature = signature
		ctx.sum_index = sum_index
		
		# Get the size nx by looping on the signature until we've found an "x_i" ----------------
		nx = -1
		for ( index, (dim,cat) ) in enumerate(signature[1:]) : # Omit the output
			if cat == 0 :
				nx = len( args[index] ) # Lengths compatibility is done by cuda_conv_generic
				break
		if nx == -1 : raise ValueError("The signature should contain at least on indexing argument x_i.")
		
		# Data Conversion (only CPU via numpy implented at the moment) --------------------------
		
		args_conv = [ arg.numpy() for arg in args]
		
	                  
		# Actual computation --------------------------------------------------------------------
		result  = torch.zeros( nx * signature[0][0] ).type(dtype) # Init the output of the convolution
		cuda_conv_generic(formula, result, *args_conv,            # Inplace CUDA routine
		                  aliases = aliases, sum_index = sum_index,
		                  cuda_type = "float", grid_scheme = "2D") 
		result  = result.view( nx, signature[0][0] )
		return result
	
	@staticmethod
	def backward(ctx, a):
		""" Backward scheme: 
			given a dual output vector "a_i" represented by a N-by-D array (i from 1 to N),
			outputs :
			- \partial_s K(s,x,y,b) . a, which is a float number (NOT IMPLEMENTED YET)
			- \partial_x K(s,x,y,b) . a, which is a N-by-D array
			- \partial_y K(s,x,y,b) . a, which is a M-by-D array
			- \partial_b K(s,x,y,b) . a, which is a M-by-E array, equal to K(s,y,x,a).		
		"""
		(ss, xx, yy, bb) = ctx.saved_variables # Unwrap the saved variables
		kernel = ctx.kernel
		# In order to get second derivatives, we encapsulated the cudagradconv.cuda_gradconv
		# routine in another torch.autograd.Function object:
		kernelproductgrad_x = KernelProductGrad_x().apply 
		
		# Compute \partial_s K(s,x,y,b) . a   -------------NOT IMPLEMENTED YET-------------------
		grad_s = None
		
		# Compute \partial_x K(s,x,y,b) . a   --------------------------------------------------- 
		# We're looking for the gradient with respect to x of
		# < a, K(s,x,y,b) >  =  \sum_{i,j} f_s( |x_i-y_j|^2 ) < a_i, b_j >
		# kernelproductgrad_x computes the gradient, with respect to the 3rd variable x, of trace(
		grad_x = kernelproductgrad_x( ss, a,  #     a^T
								      xx, yy, #   @ K(x,y)
								      bb,     #   @ b )
									  kernel)
		# Compute \partial_y K(s,x,y,b) . a   --------------------------------------------------- 
		# We're looking for the gradient with respect to y of
		# < a, K(s,x,y,b) >  =  \sum_{i,j} f_s( |x_i-y_j|^2 ) < a_i, b_j >
		# Thanks to the symmetry in (x,a) and (y,b) of the above formula,
		# we can use the same cuda code as the one that was used for grad_x:
		# kernelproductgrad_x computes the gradient, with respect to the 3rd variable y, of trace(
		grad_y = kernelproductgrad_x( ss, bb, #     b^T
								      yy, xx, #   @ K(y,x)
								      a,      #   @ a )
									  kernel) 
		# Compute \partial_b K(s,x,y,b) . a   --------------------------------------------------- 
		Kt = KernelProduct().apply # Will be used to compute the kernel "transpose"
		grad_b = Kt(    ss,      # We use the same kernel scale
		                yy, xx,  # But we compute K_yx, instead of K_xy
		                a,       # And multiply it with a         
		                kernel)
		return (grad_s, grad_x, grad_y, grad_b, None)

class KernelProductGrad_x(torch.autograd.Function):
	""" This class implements the gradient of the above operator
		'KernelProduct' with respect to its second variable, 'x'.
		If:
		- s   is a scale   ("sigma")
		- a_i is an N-by-E array  (i from 1 to N)
		- x_i is an N-by-D array  (i from 1 to N)
		- y_j is an M-by-D array  (j from 1 to M)
		- b_j is an M-by-E array  (j from 1 to M)
		
		Then:
		KernelProductGrad_x( s, a, x, y, b) is an N-by-D array,
		whose i-th line is given by
		KernelProduct( s, a, x, y, b)_i = \sum_j f_s'( |x_i-y_j|^2 ) * < a_i, b_j> * 2(x_i-y_j).
		
		This class wasn't designed to be used by end-users, but to provide the second derivatives
		of the operator 'KernelProduct', encoded in KernelProductGrad_x's backwars operator.
		
		f is a real-valued function which encodes the kernel operation:
		
		                 k_s(x,y)  =  f_s( |x_i-y_j|^2 )
		
		Computations are performed with CUDA on the GPU, using the 'libkp' files.                 
		This code was designed for memory efficiency: the kernel matrix is computed "one tile
		after another", and never stored in memory, be it on the GPU or on the RAM.
		
		N.B.: f and its derivatives f', f'' are hardcoded in the 'libkp/kernels.cx' file.
		
		Author: Jean Feydy
	"""
	
	@staticmethod
	def forward(ctx, s, a, x, y, b, kernel):
		""" 
		KernelProduct(s, a, x, y, b)_i = \sum_j f_s'( |x_i-y_j|^2 ) * < a_i, b_j> * 2(x_i-y_j).
		"""
		# save everything to compute the gradient
		#ctx.ss = s ; ctx.aa = a ; ctx.xx = x # TOO NAIVE!
		#ctx.yy = y ; ctx.bb = b              # We should save variables explicitly
		# N.B.: relying on the "ctx.saved_variables" attribute is necessary
		#       if you want to be able to differentiate the output of the backward
		#       once again. It helps pytorch to keep track of "who is who".
		#       As we haven't implemented the "3rd" derivative of KernelProduct,
		#       this formulation is not strictly necessary here... 
		#       But I think it is good practice anyway.
		ctx.save_for_backward( s, a, x, y, b )   # Call at most once in the "forward".
		ctx.kernel = kernel
		
		# init grad_x which contains the output
		grad_x = torch.zeros(x.numel()).type(dtype) #0d array
		# We're looking for the gradient with respect to x of
		# < a, K(s,x,y,b) >  =  \sum_{i,j} f_s( |x_i-y_j|^2 ) < a_i, b_j >
		# Cudagradconv computes the gradient, with respect to x, of trace(
		cudagrad1conv.cuda_grad1conv( a.numpy(),            #     a^T
								      x.numpy(), y.numpy(), #   @ K(x,y)
								      b.numpy(),            #   @ b )
								      grad_x.numpy(),       # Output array
								      s.numpy(),            # Kernel scale parameter
								      kernel = kernel)
		grad_x = grad_x.view(x.shape)
		
		return grad_x
	
	@staticmethod
	def backward(ctx, e):
		""" Backward scheme: 
			given a dual output vector "e_i" represented by a N-by-D array (i from 1 to N),
			outputs :
			- \partial_s Kx(s,a,x,y,b) . e, which is a float number (NOT IMPLEMENTED YET)
			- \partial_a Kx(s,a,x,y,b) . e, which is a N-by-E array
			- \partial_x Kx(s,a,x,y,b) . e, which is a N-by-D array
			- \partial_y Kx(s,a,x,y,b) . e, which is a M-by-D array
			- \partial_b Kx(s,a,x,y,b) . e, which is a M-by-E array, equal to K(s,y,x,a).		
		"""
		(ss, aa, xx, yy, bb) = ctx.saved_variables # Unwrap the saved variables
		kernel = ctx.kernel
		
		
		
		# Compute \partial_s Kx(s,a,x,y,b) . e   ------------NOT IMPLEMENTED YET-----------------
		grad_xs = None
		
		# Compute \partial_a Kx(s,a,x,y,b) . e   ------------------------------------------------ 
		# We're looking for the gradient with respect to a of
		#
		# < e, K(s,a,x,y,b) >  =  \sum_{i,j} f_s'( |x_i-y_j|^2 ) * < a_i, b_j > * 2 < e_i, x_i-y_j>,
		#
		# which is an N-by-E array g_i (i from 1 to N), where each line is equal to
		#
		# g_i  =  \sum_j 2* f_s'( |x_i-y_j|^2 ) * < e_i, x_i-y_j> * b_j
		#
		# This is what cuda_gradconv_xa is all about:
		
		grad_xa = torch.zeros( aa.numel() ).type(dtype) #0d array
		cudagradgradconv.cuda_gradconv_xa( e.data.numpy(),
										   aa.data.numpy(),
										   xx.data.numpy(), yy.data.numpy(),
										   bb.data.numpy(),
										   grad_xa.numpy(),  # Output array
										   ss.data.numpy(),
										   kernel = kernel ) 
		grad_xa  = Variable(grad_xa.view( aa.size()[0], aa.size()[1] ))
		
		# Compute \partial_x Kx(s,a,x,y,b) . e   ------------------------------------------------ 
		# We're looking for the gradient with respect to x of
		#
		# < e, K(s,a,x,y,b) >  =  \sum_{i,j} f_s'( |x_i-y_j|^2 ) * < a_i, b_j > * 2 < e_i, x_i-y_j>,
		#
		# which is an N-by-D array g_i (i from 1 to N), where each line is equal to
		#
		# g_i  =  2* \sum_j < a_i, b_j > * [                       f_s'(  |x_i-y_j|^2 ) * e_i
		#                                  + 2* < x_i-y_j, e_i > * f_s''( |x_i-y_j|^2 ) * (x_i-y_j) ]
		#
		# This is what cuda_gradconv_xx is all about:
		
		grad_xx = torch.zeros( xx.numel() ).type(dtype) #0d array
		cudagradgradconv.cuda_gradconv_xx(  e.data.numpy(),
										   aa.data.numpy(),
										   xx.data.numpy(), yy.data.numpy(),
										   bb.data.numpy(),
										   grad_xx.numpy(),  # Output array
										   ss.data.numpy(),
										   kernel = kernel  ) 
		grad_xx  = Variable(grad_xx.view( xx.size()[0], xx.size()[1] ))
		
		# Compute \partial_y Kx(s,a,x,y,b) . e   ------------------------------------------------ 
		# We're looking for the gradient with respect to y of
		#
		# < e, K(s,a,x,y,b) >  =  \sum_{i,j} f_s'( |x_i-y_j|^2 ) * < a_i, b_j > * 2 < e_i, x_i-y_j>,
		#
		# which is an M-by-D array g_j (j from 1 to M), where each line is equal to
		#
		# g_j  = -2* \sum_i < a_i, b_j > * [                       f_s'(  |x_i-y_j|^2 ) * e_i
		#    "don't forget the -2 !"       + 2* < x_i-y_j, e_i > * f_s''( |x_i-y_j|^2 ) * (x_i-y_j) ]
		#
		# This is what cuda_gradconv_xy is all about:
		
		grad_xy = torch.zeros( yy.numel() ).type(dtype) #0d array
		cudagradgradconv.cuda_gradconv_xy(  e.data.numpy(),
										   aa.data.numpy(),
										   xx.data.numpy(), yy.data.numpy(),
										   bb.data.numpy(),
										   grad_xy.numpy(),  # Output array
										   ss.data.numpy(),
										   kernel = kernel ) 
		grad_xy  = Variable(grad_xy.view( yy.size()[0], yy.size()[1] ))
		
		# Compute \partial_b Kx(s,a,x,y,b) . e   ------------------------------------------------ 
		# We're looking for the gradient with respect to b of
		#
		# < e, K(s,a,x,y,b) >  =  \sum_{i,j} f_s'( |x_i-y_j|^2 ) * < a_i, b_j > * 2 < e_i, x_i-y_j>,
		#
		# which is an M-by-E array g_j (j from 1 to M), where each line is equal to
		#
		# g_j  =  \sum_i 2* f_s'( |x_i-y_j|^2 ) * < e_i, x_i-y_j> * a_i
		#
		# This is what cuda_gradconv_xb is all about:
		
		grad_xb = torch.zeros( bb.numel() ).type(dtype) #0d array
		cudagradgradconv.cuda_gradconv_xb(  e.data.numpy(),
										   aa.data.numpy(),
										   xx.data.numpy(), yy.data.numpy(),
										   bb.data.numpy(),
										   grad_xb.numpy(),  # Output array
										   ss.data.numpy(),
										   kernel = kernel ) 
		grad_xb  = Variable(grad_xb.view( bb.size()[0], bb.size()[1] ))
		
		
		return (grad_xs, grad_xa, grad_xx, grad_xy, grad_xb, None)



if __name__ == "__main__":
	# from visualize import make_dot
	
	backend = "libkp" # Other value : 'pytorch'
	
	if   backend == "libkp" :
		kernel_product        = KernelProduct().apply
		kernel_product_grad_x = KernelProductGrad_x().apply
	elif backend == "pytorch" :
		def kernel_product(s, x, y, b, kernel) :
			x_col = x.unsqueeze(1) # Theano : x.dimshuffle(0, 'x', 1)
			y_lin = y.unsqueeze(0) # Theano : y.dimshuffle('x', 0, 1)
			sq    = torch.sum( (x_col - y_lin)**2 , 2 )
			K_xy  = torch.exp( -sq / (s**2))
			return K_xy @ b
			
			
			
	#--------------------------------------------------#
	# Init variables to get a minimal working example:
	#--------------------------------------------------#
	dtype = torch.FloatTensor
	
	N = 10 ; M = 15 ; D = 3 ; E = 3
	
	e = .6 * torch.linspace(  0, 5,N*D).type(dtype).view(N,D)
	e = torch.autograd.Variable(e, requires_grad = True)
	
	a = .6 * torch.linspace(  0, 5,N*E).type(dtype).view(N,E)
	a = torch.autograd.Variable(a, requires_grad = True)
	
	x = .6 * torch.linspace(  0, 5,N*D).type(dtype).view(N,D)
	x = torch.autograd.Variable(x, requires_grad = True)
	
	y = .2 * torch.linspace(  0, 5,M*D).type(dtype).view(M,D)
	y = torch.autograd.Variable(y, requires_grad = True)
	
	b = .6 * torch.linspace(-.2,.2,M*E).type(dtype).view(M,E)
	b = torch.autograd.Variable(b, requires_grad = True)
	
	s = torch.Tensor([2.5]).type(dtype)
	s = torch.autograd.Variable(s, requires_grad = False)
	
	#--------------------------------------------------#
	# check the class KernelProductGrad_x routines
	#--------------------------------------------------#
	
	if False :
		grad_x = kernel_product_grad_x(s, a, x, y, b, "gaussian")
		(grad_xa, grad_xx, grad_xy, grad_xb) = torch.autograd.grad( grad_x, (a,x,y,b), e)
	
	if False :
		print("grad_x  :\n",  grad_x.data.numpy())
		print("grad_xa :\n", grad_xa.data.numpy())
		print("grad_xx :\n", grad_xx.data.numpy())
		print("grad_xy :\n", grad_xy.data.numpy())
		print("grad_xb :\n", grad_xb.data.numpy())
	
	
	#--------------------------------------------------#
	# check the class KernelProduct
	#--------------------------------------------------#
	def Ham(q,p) :
		Kq_p  = kernel_product(s,q,q,p, "gaussian")
		# make_dot(Kq_p, {'q':q, 'p':p, 's':s}).render('graphs/Kqp_'+backend+'.pdf', view=True)
		return torch.dot( p.view(-1), Kq_p.view(-1) )
	
	ham0   = Ham(y, b)
	# make_dot(ham0, {'y':y, 'b':b, 's':s}).render('graphs/ham0_'+backend+'.pdf', view=True)
	
	print('----------------------------------------------------')
	print("Ham0:")
	print(ham0)
	
	grad_y = torch.autograd.grad(ham0,y,create_graph = True)[0]
	grad_b = torch.autograd.grad(ham0,b,create_graph = True)[0]
	
	print('grad_y  :\n', grad_y.data.numpy())
	print('grad_b  :\n', grad_b.data.numpy())
	
	
	# make_dot(grad_y, {'y':y, 'b':b, 's':s}).render('graphs/grad_y_'+backend+'.pdf', view=True)
	print('grad_y :\n', grad_y.data.numpy())
	
	if False :
		def to_check( X, Y, B ):
			return kernel_product(s, X, Y, B, "gaussian")
		gc = torch.autograd.gradcheck(to_check, inputs=(x, y, b) , eps=1e-4, atol=1e-3, rtol=1e-3 )
		print('Gradcheck for Hamiltonian: ',gc)
		print('\n')

	#--------------------------------------------------#
	# check that we are able to compute derivatives with autograd
	#--------------------------------------------------#
	
	if False :
		grad_b_sum = torch.dot(grad_b.view(-1), grad_b.view(-1))
		# make_dot(grad_b_sum, {'y':y, 'b':b, 's':s}).render('graphs/grad_b_sum_'+backend+'.pdf', view=True)
		print('grad_b_sum :\n', grad_b_sum.data.numpy())
		
		grad_b_sum_b  = torch.autograd.grad(grad_b_sum,b,create_graph = True)[0]
		make_dot(grad_b_sum_b, {'y':y, 'b':b, 's':s}).render('graphs/grad_b_sum_b_'+backend+'.pdf', view=True)
		print('grad_b_sum_b :\n', grad_b_sum_b.data.numpy())
	
	if True :
		# N.B. : As of October 2017, there's clearly a type problem within pytorch's implementation
		#        of sum's backward operator - I looks as though they naively pass an array of
		#        "1" to the backward operator
		# grad_y_sum = grad_y.sum() # backward will be randomish, due to type conversion issues
		Ones = Variable(torch.ones( grad_y.numel() ).type(dtype))
		grad_y_sum = torch.dot(grad_y.view(-1), Ones )
		# make_dot(grad_y_sum, {'y':y, 'b':b, 's':s}).render('graphs/grad_y_sum_'+backend+'.pdf', view=True)
		print('grad_y_sum :\n', grad_y_sum.data.numpy())
		
		grad_y_sum_y  = torch.autograd.grad(grad_y_sum,y,create_graph = True)[0]
		# make_dot(grad_y_sum_y, {'y':y, 'b':b, 's':s}).render('graphs/grad_y_sum_y_'+backend+'.pdf', view=True)
		print('grad_y_sum_y :\n', grad_y_sum_y.data.numpy())
		
		
		grad_y_sum_b  = torch.autograd.grad(grad_y_sum,b,create_graph = True)[0]
		# make_dot(grad_y_sum_b, {'y':y, 'b':b, 's':s}).render('graphs/grad_y_sum_b_'+backend+'.pdf', view=True)
		print('grad_y_sum_b :\n', grad_y_sum_b.data.numpy())
	
	
	#--------------------------------------------------#
	# check that we are able to compute derivatives with autograd
	#--------------------------------------------------#
	if False :
		q1 = .6 * torch.linspace(0,5,n*d).type(dtype).view(n,d)
		q1 = torch.autograd.Variable(q1, requires_grad = True)

		p1 = .5 * torch.linspace(-.2,.2,n*d).type(dtype).view(n,d)
		p1 = torch.autograd.Variable(p1, requires_grad = True)
		sh = torch.sin(ham)

		gsh = torch.autograd.grad( sh , p1, create_graph = True)[0]
		print('derivative of sin(ham): ', gsh)
		print(gsh.volatile)

		ngsh = gsh.sum()

		ggsh = torch.autograd.grad( ngsh , p1)
		print('derivative of sin(ham): ', ggsh)
