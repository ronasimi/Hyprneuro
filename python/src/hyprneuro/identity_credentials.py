"""Read only the credential configuration of a closed manager unit.

systemctl renders even empty binary credential arrays as '[unprintable]'. One
supported sd-bus connection holds LoadUnit and all property reads together, so an
inactive pre-start unit cannot be GC'd between separate CLI connections. No
credential bytes, arbitrary methods, unit starts or diagnostics are exposed.
"""
import asyncio
import ctypes as C
import re


def _read(unit):
    if not isinstance(unit,str) or not re.fullmatch(r'[A-Za-z0-9_.@\\-]+\.service',unit):
        raise PermissionError('Invalid closed credential unit')
    lib=C.CDLL('/usr/lib/libsystemd.so.0')
    ptr=C.c_void_p
    lib.sd_bus_open_user.argtypes=[C.POINTER(ptr)]
    lib.sd_bus_set_method_call_timeout.argtypes=[ptr,C.c_uint64]
    lib.sd_bus_message_unref.argtypes=[ptr];lib.sd_bus_message_unref.restype=ptr
    lib.sd_bus_flush_close_unref.argtypes=[ptr];lib.sd_bus_flush_close_unref.restype=ptr
    lib.sd_bus_message_enter_container.argtypes=[ptr,C.c_char,C.c_char_p]
    lib.sd_bus_message_exit_container.argtypes=[ptr]
    lib.sd_bus_message_at_end.argtypes=[ptr,C.c_int]
    # The remaining functions are documented C variadic sd-bus APIs. Explicit
    # pointer/string wrappers are required; never allow ctypes' default int cast.
    bus=ptr();message=ptr()
    def check(result):
        if result<0:raise PermissionError('Manager credential observation failed')
        return result
    destination=C.c_char_p(b'org.freedesktop.systemd1')
    interface=C.c_char_p(b'org.freedesktop.systemd1.Service')
    try:
        check(lib.sd_bus_open_user(C.byref(bus)))
        check(lib.sd_bus_set_method_call_timeout(bus,3_000_000))
        check(lib.sd_bus_call_method(bus,destination,C.c_char_p(b'/org/freedesktop/systemd1'),
            C.c_char_p(b'org.freedesktop.systemd1.Manager'),C.c_char_p(b'LoadUnit'),ptr(),
            C.byref(message),C.c_char_p(b's'),C.c_char_p(unit.encode())))
        path=C.c_char_p()
        check(lib.sd_bus_message_read(message,C.c_char_p(b'o'),C.byref(path)))
        object_path=C.c_char_p(bytes(path.value))
        lib.sd_bus_message_unref(message);message=ptr()
        result={}
        for key in ['LoadCredential','LoadCredentialEncrypted','SetCredential','SetCredentialEncrypted','ImportCredential','ImportCredentialEx']:
            try:
                rc=lib.sd_bus_get_property(bus,destination,object_path,interface,C.c_char_p(key.encode()),
                    ptr(),C.byref(message),C.c_char_p(b'as' if key=='ImportCredential' else b'a(ss)' if key.startswith('LoadCredential') or key=='ImportCredentialEx' else b'a(say)'))
                if rc<0:raise PermissionError('Manager credential property unavailable: '+key)
                check(lib.sd_bus_message_enter_container(message,b'a',b'(ss)' if key=='LoadCredential' else None))
                if key=='LoadCredential':
                    pairs=[]
                    while not check(lib.sd_bus_message_at_end(message,0)):
                        if len(pairs)>=16:raise PermissionError('Too many credential sources')
                        check(lib.sd_bus_message_enter_container(message,b'r',b'ss'))
                        name=C.c_char_p();source=C.c_char_p()
                        check(lib.sd_bus_message_read(message,C.c_char_p(b'ss'),C.byref(name),C.byref(source)))
                        if len(name.value)>4096 or len(source.value)>4096:raise PermissionError('Oversized credential source')
                        pairs.append([name.value.decode(),source.value.decode()])
                        check(lib.sd_bus_message_exit_container(message))
                    result[key]=pairs
                else:
                    result[key]=not bool(check(lib.sd_bus_message_at_end(message,0)))
            finally:
                if message:lib.sd_bus_message_unref(message);message=ptr()
        return result
    finally:
        if message:lib.sd_bus_message_unref(message)
        if bus:lib.sd_bus_flush_close_unref(bus)


async def read_credentials(unit):
    return await asyncio.to_thread(_read,unit)


def require_root_credential(value,source):
    if (set(value)!={'LoadCredential','LoadCredentialEncrypted','SetCredential','SetCredentialEncrypted','ImportCredential','ImportCredentialEx'}
            or value['LoadCredential']!=[['main-root-sha',str(source)]]
            or any(value[k] is not False for k in value if k!='LoadCredential')):
        raise PermissionError('Exact manager-delivered MAIN credential required')
