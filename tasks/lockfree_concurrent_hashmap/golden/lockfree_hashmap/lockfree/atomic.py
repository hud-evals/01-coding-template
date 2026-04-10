import ctypes
import os
import sys

# Machine code for atomic compare and swap (x86_64)
# Parameters (System V ABI - Linux/macOS): rdi=ptr, rsi=expected, rdx=new
# Parameters (Windows x64 ABI): rcx=ptr, rdx=expected, r8=new
# Returns: bool (rax = 1 for success, 0 for fail)

def get_cas_64():
    # Linux/SysV ABI Stub:
    # mov rax, rsi
    # lock cmpxchg [rdi], rdx
    # sete al
    # movzx rax, al
    # ret
    mc_linux = b"\x48\x89\xf0\xf0\x48\x0f\xb1\x17\x0f\x94\xc0\x48\x0f\xb6\xc0\xc3"
    
    # Windows x64 ABI Stub:
    # mov rax, rdx
    # lock cmpxchg [rcx], r8
    # sete al
    # movzx rax, al
    # ret
    mc_windows = b"\x48\x89\xd0\xf0\x4c\x0f\xb1\x01\x0f\x94\xc0\x48\x0f\xb6\xc0\xc3"

    try:
        if os.name == 'nt':
            # Windows: VirtualAlloc
            kernel32 = ctypes.windll.kernel32
            VirtualAlloc = kernel32.VirtualAlloc
            VirtualAlloc.restype = ctypes.c_void_p
            VirtualAlloc.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_ulong, ctypes.c_ulong]
            
            MEM_COMMIT = 0x1000
            PAGE_EXECUTE_READWRITE = 0x40
            
            addr = VirtualAlloc(None, len(mc_windows), MEM_COMMIT, PAGE_EXECUTE_READWRITE)
            if not addr: return None
            ctypes.memmove(addr, mc_windows, len(mc_windows))
        else:
            # Linux/Unix: mmap
            import mmap
            buf = mmap.mmap(-1, 4096, prot=mmap.PROT_READ | mmap.PROT_WRITE | mmap.PROT_EXEC)
            buf.write(mc_linux)
            addr = ctypes.addressof(ctypes.c_char.from_buffer(buf))
            global _mmap_buf
            _mmap_buf = buf

        ftype = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.POINTER(ctypes.c_longlong), ctypes.c_longlong, ctypes.c_longlong)
        return ftype(addr)
    except Exception:
        return None

_cas_64 = get_cas_64()

class AtomicInteger:
    """
    A thread-safe integer supporting atomic compare-and-swap.
    Uses ctypes to bypass Python object reference counting
    and achieve atomic reads/writes on CPython.
    """
    def __init__(self, value: int = 0):
        self._val = ctypes.c_longlong(value)

    def get(self) -> int:
        return self._val.value

    def set(self, value: int) -> None:
        self._val.value = value

    def compare_and_swap(self, expected: int, new_value: int) -> bool:
        if not _cas_64:
            # Atomic assignment fallback for GIL-protected environments if hardware atomics fail to load
            if self._val.value == expected:
                self._val.value = new_value
                return True
            return False
        return _cas_64(ctypes.byref(self._val), expected, new_value)

    cas = compare_and_swap

    def increment(self) -> int:
        while True:
            old = self.get()
            if self.cas(old, old + 1):
                return old + 1

    def decrement(self) -> int:
        while True:
            old = self.get()
            if self.cas(old, old - 1):
                return old - 1

    def fetch_and_add(self, delta: int) -> int:
        while True:
            old = self.get()
            if self.cas(old, old + delta):
                return old

class AtomicReference:
    """
    A thread-safe object reference supporting atomic compare-and-swap.
    Stores Python object references; CAS uses object identity (is), not equality (==).
    """
    def __init__(self, value=None):
        self._ptr = AtomicInteger(id(value))
        self._value_holder = value 

    def get(self) -> object:
        # id() gives address, cast back to py_object
        ptr_val = self._ptr.get()
        return ctypes.cast(ptr_val, ctypes.py_object).value

    def set(self, value) -> None:
        self._ptr.set(id(value))
        self._value_holder = value

    def compare_and_swap(self, expected, new_value) -> bool:
        if self._ptr.cas(id(expected), id(new_value)):
            self._value_holder = new_value 
            return True
        return False

    cas = compare_and_swap

EMPTY = object()
DELETED = object()
RESIZING = object()
