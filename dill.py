# -*- coding: utf-8 -*-
"""
dill: a full python state pickler

Based on code written by Oren Tirosh and Armin Ronacher.
Extended to a (near) full set of python types (in types module),
and coded to the pickle interface, by mmckerns@caltech.edu
"""
__all__ = ['dump','dumps','load','loads','dump_session','load_session',\
           'Pickler','Unpickler','register','copy','pickle','pickles']

import __builtin__
import __main__ as _main_module
import sys
import marshal
import ctypes
from pickle import HIGHEST_PROTOCOL, PicklingError
from pickle import Pickler as StockPickler
from pickle import Unpickler as StockUnpickler
from types import CodeType, FunctionType, ClassType, MethodType, \
     GeneratorType, DictProxyType, XRangeType, SliceType, TracebackType, \
     NotImplementedType, EllipsisType, MemberDescriptorType, FrameType, \
     ModuleType, GetSetDescriptorType, BuiltinMethodType 
from weakref import ReferenceType, ProxyType, CallableProxyType

CellType = type((lambda x: lambda y: x)(0).func_closure[0])
WrapperDescriptorType = type(type.__repr__)
MethodDescriptorType = type(type.__dict__['mro'])

### Shorthands (modified from python2.5/lib/pickle.py)
try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

def copy(obj):
    """use pickling to 'copy' an object"""
    return loads(dumps(obj))

def dump(obj, file, protocol=HIGHEST_PROTOCOL):
    """pickle an object to a file"""
    pik = Pickler(file, protocol)
    pik._main_module = _main_module
    pik.dump(obj)
    return

def dumps(obj, protocol=HIGHEST_PROTOCOL):
    """pickle an object to a string"""
    file = StringIO()
    dump(obj, file, protocol)
    return file.getvalue()

def load(file):
    """unpickle an object from a file"""
    pik = Unpickler(file)
    pik._main_module = _main_module
    obj = pik.load()
   #_main_module.__dict__.update(obj.__dict__) #XXX: should update globals ?
    return obj

def loads(str):
    """unpickle an object from a string"""
    file = StringIO(str)
    return load(file)

### End: Shorthands ###

### Pickle the Interpreter Session
def dump_session(filename='/tmp/console.sess', main_module=_main_module):
    """pickle the current state of __main__ to a file"""
    f = file(filename, 'wb')
    try:
        pickler = Pickler(f, 2)
        pickler._main_module = main_module
        pickler.dump(main_module)
    finally:
        f.close()
    return

def load_session(filename='/tmp/console.sess', main_module=_main_module):
    """update the __main__ module with the state from the session file"""
    f = file(filename, 'rb')
    try:
        unpickler = Unpickler(f)
        unpickler._main_module = main_module
        module = unpickler.load()
        main_module.__dict__.update(module.__dict__)
    finally:
        f.close()
    return

### End: Pickle the Interpreter

### Extend the Picklers
class Pickler(StockPickler):
    dispatch = StockPickler.dispatch.copy()
    _main_module = None
    pass

class Unpickler(StockUnpickler):
    _main_module = None

    def find_class(self, module, name):
        if (module, name) == ('__builtin__', '__main__'):
            return self._main_module.__dict__ #XXX: above set w/save_module_dict
        return StockUnpickler.find_class(self, module, name)
    pass

def pickle(ob_type, pickle_function):
    """expose dispatch table for user-created extensions"""
    Pickler.dispatch[t] = func
    return

def register(t):
    def proxy(func):
        Pickler.dispatch[t] = func
        return func
    return proxy

def _create_typemap():
    import types
    for key, value in types.__dict__.iteritems():
        if getattr(value, '__module__', None) == '__builtin__' and \
           type(value) is type:
            yield value, key
    return
_typemap = dict(_create_typemap(), **{
    CellType:                   'CellType',
    WrapperDescriptorType:      'WrapperDescriptorType',
    MethodDescriptorType:       'MethodDescriptorType'
})
_reverse_typemap = dict((v, k) for k, v in _typemap.iteritems())

def _unmarshal(string):
    return marshal.loads(string)

def _load_type(name):
    return _reverse_typemap[name]

def _create_type(type, *args):
    return type(*args)

ctypes.pythonapi.PyCell_New.restype = ctypes.py_object
ctypes.pythonapi.PyCell_New.argtypes = [ctypes.py_object]
# thanks to Paul Kienzle for cleaning the ctypes CellType logic
def _create_cell(obj):
     return ctypes.pythonapi.PyCell_New(obj)

ctypes.pythonapi.PyDictProxy_New.restype = ctypes.py_object
ctypes.pythonapi.PyDictProxy_New.argtypes = [ctypes.py_object]
def _create_dictproxy(obj, *args):
     dprox = ctypes.pythonapi.PyDictProxy_New(obj)
     #XXX: hack to take care of pickle 'nesting' the correct dictproxy
     if 'nested' in args and type(dprox['__dict__']) == DictProxyType:
         return dprox['__dict__']
     return dprox

ctypes.pythonapi.PyWeakref_GetObject.restype = ctypes.py_object
ctypes.pythonapi.PyWeakref_GetObject.argtypes = [ctypes.py_object]
def _create_weakref(obj, *args):
     from weakref import ref, ReferenceError
     if obj: return ref(obj) #XXX: callback?
     raise ReferenceError, "Cannot pickle reference to dead object"

def _create_weakproxy(obj, *args):
     from weakref import proxy, ReferenceError
     if obj: return proxy(obj) #XXX: callback?
     raise ReferenceError, "Cannot pickle reference to dead object"

def _eval_repr(repr_str):
    return eval(repr_str)

def _getattr(objclass, name, repr_str):
    # hack to grab the reference directly
    try: #XXX: works only for __builtin__ ?
        attr = repr_str.split("'")[3]
        return eval(attr+'.__dict__["'+name+'"]')
    except:
        return getattr(objclass,name)

def _dict_from_dictproxy(dictproxy):
     _dict = dictproxy.copy() # convert dictproxy to dict
     _dict.pop('__dict__')
     try: # new classes have weakref (while not all others do)
         _dict.pop('__weakref__')
     except KeyError:
         pass
     return _dict

def _import_module(import_name):
    if '.' in import_name:
        items = import_name.split('.')
        module = '.'.join(items[:-1])
        obj = items[-1]
    else:
        return __import__(import_name)
    return getattr(__import__(module, None, None, [obj]), obj)

def _locate_function(obj):
    if obj.__module__ == '__main__':
        return False
    try:
        found = _import_module(obj.__module__ + '.' + obj.__name__)
    except:
        return False
    return found is obj

@register(CodeType)
def save_code(pickler, obj):
    pickler.save_reduce(_unmarshal, (marshal.dumps(obj),), obj=obj)
    return

@register(FunctionType)
def save_function(pickler, obj):
    if not _locate_function(obj):
        pickler.save_reduce(FunctionType, (obj.func_code, obj.func_globals,
                                           obj.func_name, obj.func_defaults,
                                           obj.func_closure), obj=obj)
    else:
        StockPickler.save_global(pickler, obj)
    return

@register(dict)
def save_module_dict(pickler, obj):
    if obj is pickler._main_module.__dict__:
        pickler.write('c__builtin__\n__main__\n')
    else:
        StockPickler.save_dict(pickler, obj)
    return

@register(ClassType)
def save_classobj(pickler, obj):
    if obj.__module__ == '__main__':
        pickler.save_reduce(ClassType, (obj.__name__, obj.__bases__,
                                        obj.__dict__), obj=obj)
                                       #XXX: or obj.__dict__.copy()), obj=obj) ?
    else:
        StockPickler.save_global(pickler, obj)
    return

@register(MethodType)
def save_instancemethod(pickler, obj):
    pickler.save_reduce(MethodType, (obj.im_func, obj.im_self,
                                     obj.im_class), obj=obj)
    return

@register(BuiltinMethodType)
def save_builtin_method(pickler, obj):
    if obj.__self__ is not None:
        pickler.save_reduce(getattr, (obj.__self__, obj.__name__), obj=obj)
    else:
        StockPickler.save_global(pickler, obj)
    return

@register(MemberDescriptorType)
@register(GetSetDescriptorType)
@register(MethodDescriptorType)
@register(WrapperDescriptorType)
def save_wrapper_descriptor(pickler, obj):
    pickler.save_reduce(_getattr, (obj.__objclass__, obj.__name__,
                                   obj.__repr__()), obj=obj)
    return

@register(CellType)
def save_cell(pickler, obj):
    pickler.save_reduce(_create_cell, (obj.cell_contents,), obj=obj)
    return

@register(DictProxyType)
def save_dictproxy(pickler, obj):
    pickler.save_reduce(_create_dictproxy, (dict(obj),'nested'), obj=obj)
    return

@register(SliceType)
def save_slice(pickler, obj):
    pickler.save_reduce(slice, (obj.start, obj.stop, obj.step), obj=obj)
    return

@register(XRangeType)
@register(EllipsisType)
@register(NotImplementedType)
def save_singleton(pickler, obj):
    pickler.save_reduce(_eval_repr, (obj.__repr__(),), obj=obj)
    return

def _locate_refobj(oid, module):
    for obj in module.__dict__.values():
        if oid == id(obj):
            return obj
    #XXX: nothing found... so return None? or Error?
    return None

"""
@register(ReferenceType)
def save_weakref(pickler, obj):
    #FIXME: creates a dead weak ref, need to preserve "refobj"
    pickler.save_reduce(_create_weakref, (obj(),), obj=obj)
    #FIXME: first need to locate the module the ref obj lives
  # refobj = _locate_refobj(obj.__hash__(), pickler._main_module )
  # pickler.save_reduce(_create_weakref, (refobj,), obj=obj)
    #FIXME: can lead to Segmentation Fault
   #ref_obj = ctypes.pythonapi.PyWeakref_GetObject(obj) # dead returns "None"
   #if ref_obj:
   #    pickler.save_reduce(_create_weakref, (ref_obj,), obj=obj)
   #else: # FIXME: dead referenced object will raise an error
   #    pickler.save_reduce(_create_weakref, (ref_obj,), obj=obj)
    return
"""

"""
@register(ProxyType)
@register(CallableProxyType)
def save_weakproxy(pickler, obj):
    ref_obj = ctypes.pythonapi.PyWeakref_GetObject(obj) # dead returns "None"
    if ref_obj:
        pickler.save_reduce(_create_weakproxy, (ref_obj,), obj=obj)
    else: # FIXME: dead referenced object will raise an error
        pickler.save_reduce(_create_weakproxy, (ref_obj,), obj=obj)
    return
"""

@register(ModuleType)
def save_module(pickler, obj):
    if obj is pickler._main_module:
        pickler.save_reduce(__import__, (obj.__name__,), obj=obj,
                            state=obj.__dict__.copy())
    else:
        pickler.save_reduce(_import_module, (obj.__name__,), obj=obj)
    return

@register(type)
def save_type(pickler, obj):
    if obj in _typemap:
        pickler.save_reduce(_load_type, (_typemap[obj],), obj=obj)
    elif obj.__module__ == '__main__':
        if type(obj) == type: #XXX: need better filter for new classes?
            _dict = _dict_from_dictproxy(obj.__dict__)
        else:
            _dict = obj.__dict__
       #print obj; print _dict
       #print "%s\n%s" % (type(obj), obj.__name__)
       #print "%s\n%s" % (obj.__bases__, obj.__dict__)
        pickler.save_reduce(_create_type, (type(obj), obj.__name__,
                                           obj.__bases__, _dict), obj=obj)
    else:
       #print obj; print obj.__dict__
       #print "%s\n%s" % (type(obj), obj.__name__)
       #print "%s\n%s" % (obj.__bases__, obj.__dict__)
        StockPickler.save_global(pickler, obj)
    return

# quick sanity checking
def pickles(obj,exact=False):
    """quick check if object pickles with dill"""
    try:
        pik = copy(obj)
        if exact:
          return pik == obj 
        return type(pik) == type(obj)
    except (TypeError, PicklingError), err:
        return False

# EOF
