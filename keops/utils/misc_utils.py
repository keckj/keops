
#######################################################################
# .  Warnings, Errors, etc.
#######################################################################


def KeOps_Message(message, **kwargs):
    message = "[KeOps] " + message
    print(message, **kwargs)

def KeOps_Warning(message):
    message = "[KeOps] Warning : " + message
    print(message)

def KeOps_Error(message, show_line_number=True):
    message = "[KeOps] Error : " + message
    if show_line_number:
        from inspect import currentframe, getframeinfo
        frameinfo = getframeinfo(currentframe().f_back)
        message += f" (error at line {frameinfo.lineno} in file {frameinfo.filename})"
    raise ValueError(message)








def find_library_abspath(lib):
    """
    wrapper around ctypes find_library that returns the full path
    of the library. 
    Warning : it also opens the shared library !
    Adapted from
    https://stackoverflow.com/questions/35682600/get-absolute-path-of-shared-library-in-python/35683698
    """
    from ctypes import c_int, c_void_p, c_char_p, CDLL, byref, cast, POINTER, Structure
    from ctypes.util import find_library

    # linkmap structure, we only need the second entry
    class LINKMAP(Structure):
        _fields_ = [("l_addr", c_void_p), ("l_name", c_char_p)]

    res = find_library(lib)
    if res is None:
        return None

    lib = CDLL(res)
    libdl = CDLL(find_library("dl"))

    dlinfo = libdl.dlinfo
    dlinfo.argtypes = c_void_p, c_int, c_void_p
    dlinfo.restype = c_int

    # gets typecasted later, I dont know how to create a ctypes struct pointer instance
    lmptr = c_void_p()

    # 2 equals RTLD_DI_LINKMAP, pass pointer by reference
    dlinfo(lib._handle, 2, byref(lmptr))

    # typecast to a linkmap pointer and retrieve the name.
    abspath = cast(lmptr, POINTER(LINKMAP)).contents.l_name

    return abspath.decode("utf-8") 