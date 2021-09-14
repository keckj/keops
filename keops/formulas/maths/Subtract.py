from keops.formulas.Operation import Broadcast
from keops.formulas.VectorizedScalarOp import VectorizedScalarOp
from keops.formulas.variables.Zero import Zero


##########################
######    Subtract   #####
##########################


class Subtract_Impl(VectorizedScalarOp):
    """the binary subtract operation"""

    string_id = "Subtract"
    print_spec = "-", "mid", 4

    def ScalarOp(self, out, arg0, arg1):
        # returns the atomic piece of c++ code to evaluate the function on arg and return
        # the result in out
        return f"{out.id} = {arg0.id}-{arg1.id};\n"

    def DiffT(self, v, gradin):
        fa, fb = self.children
        return fa.DiffT(v, gradin) - fb.DiffT(v, gradin)
    
    
    # parameters for testing the operation (optional)
    nargs = 2                   # number of arguments
    torch_op = "torch.sub"      # equivalent PyTorch operation


# N.B. The following separate function should theoretically be implemented
# as a __new__ method of the previous class, but this can generate infinite recursion problems
def Subtract(arg0, arg1):
    if isinstance(arg0, Zero):
        return -Broadcast(arg1, arg0.dim)
    elif isinstance(arg1, Zero):
        return Broadcast(arg0, arg1.dim)
    else:
        return Subtract_Impl(arg0, arg1)