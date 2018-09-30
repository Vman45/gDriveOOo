#!
# -*- coding: utf-8 -*-

#from pkgutil import iter_modules

#from com.sun.star.document import document

#def existModule(module, path):
#    return module in (name for loader, name, ispkg in iter_modules(path))

#exist = existModule('XCmisDocument', document.__path__)
#print("__init__ %s" % exist)

#from .unotools import isCmisReady

from .cmislib import CmisDocument

from .dbtools import getDbConnection, parseDateTime, unparseDateTime, registerDataBase, getItemFromResult

from .items import selectUser, mergeUser, selectItem, insertItem, needSync

from .children import isChild, updateChildren, getChildSelect

from .identifiers import checkIdentifiers, getIdentifier, isIdentifier


from .contentlib import ContentIdentifier, Row, DynamicResultSet, CommandInfo, CommandInfoChangeNotifier
from .contentlib import InteractionRequest

from .contenttools import getUri, getUcb, getUcp, getPropertiesValues, setPropertiesValues, doSync
from .contenttools import getContent, getContentEvent, getCmisProperty, getCommandInfo, updateMetaData
from .contenttools import setContentProperties, getContentInfo, mergeContent, getMediaType, updateData
from .contenttools import propertyChange, uploadItem, createNewContent, getSession, getDataContent

from .google import InputStream, getUser, getItem, getConnectionMode, updateItem
from .google import g_scheme, g_folder, g_link, g_doc

from .logger import getLogger, getLoggerSetting, setLoggerSetting, getLoggerUrl

from .unotools import getResourceLocation, createService, getStringResource, getPropertyValue
from .unotools import getFileSequence, getProperty, getPropertySetInfoChangeEvent, getSimpleFile

from .unolib import Component, Initialization, InteractionHandler, PropertiesChangeNotifier
from .unolib import PropertySetInfo, CmisPropertySetInfo, PropertySet, PropertySetInfoChangeNotifier
