#!
# -*- coding: utf_8 -*-

import uno
import unohelper

from com.sun.star.awt import XCallback
from com.sun.star.container import XChild
from com.sun.star.lang import XServiceInfo, NoSupportException
from com.sun.star.ucb import XContent, XCommandProcessor2, CommandAbortedException
from com.sun.star.ucb.ContentAction import INSERTED, REMOVED, DELETED, EXCHANGED
from com.sun.star.ucb.ConnectionMode import ONLINE, OFFLINE


from gdrive import Initialization, CommandInfo, CmisPropertySetInfo, Row, CmisDocument
from gdrive import PropertiesChangeNotifier, PropertySetInfoChangeNotifier, CommandInfoChangeNotifier
from gdrive import ContentIdentifier, PropertyContainer, InteractionRequestName
from gdrive import getContentInfo, getPropertiesValues, uploadItem, getUcb, getMimeType, getUri, getInteractionHandler
from gdrive import getUnsupportedNameClashException, getCommandIdentifier, getContentEvent
from gdrive import createService, getResourceLocation, parseDateTime, getPropertySetInfoChangeEvent
from gdrive import getSimpleFile, getCommandInfo, getProperty, getUcp
from gdrive import propertyChange, setPropertiesValues, getLogger, getCmisProperty, getPropertyValue
from gdrive import RETRIEVED, CREATED, FOLDER, FILE, RENAMED, REWRITED, TRASHED

import requests
import traceback

# pythonloader looks for a static g_ImplementationHelper variable
g_ImplementationHelper = unohelper.ImplementationHelper()
g_ImplementationName = 'com.gmail.prrvchr.extensions.gDriveOOo.DriveOfficeContent'


class DriveOfficeContent(unohelper.Base, XServiceInfo, Initialization, XContent, XChild, XCommandProcessor2, PropertyContainer,
                         PropertiesChangeNotifier, PropertySetInfoChangeNotifier, CommandInfoChangeNotifier, XCallback):
    def __init__(self, ctx, *namedvalues):
        self.ctx = ctx
        self.Logger = getLogger(self.ctx)
        level = uno.getConstantByName("com.sun.star.logging.LogLevel.INFO")
        msg = "DriveOfficeContent loading ..."
        self.Logger.logp(level, "DriveOfficeContent", "__init__()", msg)
        self.Identifier = None

        self.ContentType = 'application/vnd.oasis.opendocument'
        self.Name = 'Sans Nom'
        self.IsFolder = False
        self.IsDocument = True
        self.DateCreated = parseDateTime()
        self.DateModified = parseDateTime()
        self._Trashed = False

        self.CanAddChild = False
        self.CanRename = True
        self.IsReadOnly = False
        self.IsVersionable = False
        self._Loaded = 1

        self.IsHidden = False
        self.IsVolume = False
        self.IsRemote = False
        self.IsRemoveable = False
        self.IsFloppy = False
        self.IsCompactDisc = False

        self.listeners = []
        self.contentListeners = []
        self.propertiesListener = {}
        self.propertyInfoListeners = []
        self.commandInfoListeners = []
        self.commandIdentifier = 0

        #self.Author = 'prrvchr'
        #self.Keywords = 'clefs de recherche'
        #self.Subject = 'Test de Google DriveOfficeContent'
        self._CmisProperties = None

        self.MimeType = None

        self.initialize(namedvalues)
        
        self._commandInfo = self._getCommandInfo()
        self._propertySetInfo = self._getPropertySetInfo()

        identifier = self.getIdentifier()
        self.ObjectId = identifier.Id
        self.CanCheckOut = True
        self.CanCheckIn = True
        self.CanCancelCheckOut = True

        self.TargetURL = identifier.getContentIdentifier()
        self.BaseURI = identifier.BaseURL
        msg = "DriveOfficeContent loading Uri: %s ... Done" % identifier.getContentIdentifier()
        self.Logger.logp(level, "DriveOfficeContent", "__init__()", msg)            

    @property
    def UserName(self):
        return self.getIdentifier().User.Name
    @property
    def TitleOnServer(self):
        # LibreOffice specifique property
        return self.Name
    @property
    def Title(self):
        # LibreOffice use this property for 'transfer command' in 'command.Argument.NewTitle'
        return self.getIdentifier().Title
    @Title.setter
    def Title(self, title):
        identifier = self.getIdentifier()
        old = self.Name
        self.Name = title
        propertyChange(self, 'Name', old, title)
        event = getContentEvent(self, EXCHANGED, self, identifier)
        self.notify(event)
    @property
    def Size(self):
        return self.getIdentifier().Size
    @Size.setter
    def Size(self, size):
        identifier = self.getIdentifier()
        old = identifier.Size
        identifier.Size = size
        propertyChange(self, 'Size', old, size)
    @property
    def Trashed(self):
        return self._Trashed
    @Trashed.setter
    def Trashed(self, trashed):
        propertyChange(self, 'Trashed', self._Trashed, trashed)
        self._Trashed = trashed
    @property
    def MediaType(self):
        return self.MimeType
    @property
    def CmisProperties(self):
        print("DriveOfficeContent.CmisProperties(): 1")
        if self._CmisProperties is None:
            self._CmisProperties = self._getCmisProperties()
        return self._CmisProperties
    @property
    def Loaded(self):
        return self._Loaded
    @Loaded.setter
    def Loaded(self, loaded):
        propertyChange(self, 'Loaded', self._Loaded, loaded)
        self._Loaded = loaded
    @property
    def CasePreservingURL(self):
        return self.getIdentifier().getContentIdentifier()
    @CasePreservingURL.setter
    def CasePreservingURL(self, url):
        pass
    @property
    def CreatableContentsInfo(self):
        return ()
    @CreatableContentsInfo.setter
    def CreatableContentsInfo(self, contentinfo):
        pass

    # XCallback
    def notify(self, event):
        for listener in self.contentListeners:
            listener.contentEvent(event)

     # XChild
    def getParent(self):
        return getUcb(self.ctx).queryContent(self.getIdentifier().getParent())
    def setParent(self, parent):
        raise NoSupportException('Parent can not be set', self)

    # XContent
    def getIdentifier(self):
        return self.Identifier
    def getContentType(self):
        return self.ContentType
    def addContentEventListener(self, listener):
        if listener not in self.contentListeners:
            self.contentListeners.append(listener)
    def removeContentEventListener(self, listener):
        if listener in self.contentListeners:
            self.contentListeners.remove(listener)

    # XCommandProcessor2
    def createCommandIdentifier(self):
        return getCommandIdentifier(self)
    def execute(self, command, id, environment):
        result = None
        level = uno.getConstantByName("com.sun.star.logging.LogLevel.INFO")
        msg = "Command name: %s ..." % command.Name
        if command.Name == 'getCommandInfo':
            result = CommandInfo(self._commandInfo)
        elif command.Name == 'getPropertySetInfo':
            result = CmisPropertySetInfo(self._propertySetInfo, self._getCmisPropertySetInfo)
        elif command.Name == 'getPropertyValues':
            namedvalues = getPropertiesValues(self, command.Argument, self.Logger)
            result = Row(namedvalues)
        elif command.Name == 'setPropertyValues':
            result = setPropertiesValues(self, environment, command.Argument, self._propertySetInfo, self.Logger)
        elif command.Name == 'open':
            sf = getSimpleFile(self.ctx)
            url = self._getUrl(sf)
            if url is None:
                raise CommandAbortedException("Error while downloading file: %s" % self.Name, self)
            sink = command.Argument.Sink
            stream = uno.getTypeByName('com.sun.star.io.XActiveDataStreamer')
            if sink.queryInterface(uno.getTypeByName('com.sun.star.io.XActiveDataSink')):
                msg += " ReadOnly mode selected ..."
                sink.setInputStream(sf.openFileRead(url))
            elif not self.IsReadOnly and sink.queryInterface(stream):
                msg += " ReadWrite mode selected ..."
                sink.setStream(sf.openFileReadWrite(url))
        elif command.Name == 'insert':
            # The Insert command is only used to create a new document (File Save As)
            # it saves content from createNewContent from the parent folder
            print("DriveOfficeContent.execute(): insert %s" % command.Argument)
            identifier = self.getIdentifier()
            stream = command.Argument.Data
            sf = getSimpleFile(self.ctx)
            path = '%s/%s' % (identifier.getContentProviderScheme(), identifier.Id)
            target = getResourceLocation(self.ctx, path)
            if sf.exists(target) and not command.Argument.ReplaceExisting:
                pass
            elif stream.queryInterface(uno.getTypeByName('com.sun.star.io.XInputStream')):
                ucp = getUcp(self.ctx)
                sf.writeFile(target, stream)
                self.MimeType = getMimeType(self.ctx, stream)
                stream.closeInput()
                self.Size = sf.getSize(target)
                self.addPropertiesChangeListener(('Id', 'Name', 'Size', 'Trashed', 'Loaded'), ucp)
                propertyChange(self, 'Id', identifier.Id, CREATED | FILE)
                parent = identifier.getParent()
                event = getContentEvent(self, INSERTED, self, parent)
                ucp.queryContent(parent).notify(event)
            print("DriveOfficeContent.execute(): insert FIN")
        elif command.Name == 'delete':
            print("DriveOfficeContent.execute(): delete")
            self.Trashed = True
        elif command.Name == 'addProperty':
            print("DriveOfficeContent.addProperty():")
        elif command.Name == 'removeProperty':
            print("DriveOfficeContent.removeProperty():")
        elif command.Name == 'lock':
            print("DriveOfficeContent.lock()")
        elif command.Name == 'unlock':
            print("DriveOfficeContent.unlock()")
        elif command.Name == 'close':
            print("DriveOfficeContent.close()")
        elif command.Name == 'updateProperties':
            print("DriveOfficeContent.updateProperties()")
        elif command.Name == 'getAllVersions':
            print("DriveOfficeContent.getAllVersions()")
        elif command.Name == 'checkout':
            print("DriveOfficeContent.checkout()")
        elif command.Name == 'cancelCheckout':
            print("DriveOfficeContent.cancelCheckout()")
        elif command.Name == 'checkIn':
            print("DriveOfficeContent.checkin()")
        msg += " Done"
        self.Logger.logp(level, "DriveOfficeContent", "execute()", msg)
        return result
    def abort(self, id):
        pass
    def releaseCommandIdentifier(self, id):
        pass

    def _getUrl(self, sf):
        identifier = self.getIdentifier()
        location = '%s/%s' % (identifier.getContentProviderScheme(), identifier.Id)
        url = getResourceLocation(self.ctx, location)
        if self.Loaded == OFFLINE and sf.exists(url):
            return url
        try:
            stream = identifier.createInputStream()
            sf.writeFile(url, stream)
        except:
            return None
        else:
            self.Loaded = OFFLINE
        finally:
            stream.closeInput()
        return url

    def _getCommandInfo(self):
        commands = {}
        commands['getCommandInfo'] = getCommandInfo('getCommandInfo')
        commands['getPropertySetInfo'] = getCommandInfo('getPropertySetInfo')
        commands['getPropertyValues'] = getCommandInfo('getPropertyValues', '[]com.sun.star.beans.Property')
        commands['setPropertyValues'] = getCommandInfo('setPropertyValues', '[]com.sun.star.beans.Property')
        commands['open'] = getCommandInfo('open', 'com.sun.star.ucb.OpenCommandArgument2')
        commands['insert'] = getCommandInfo('insert', 'com.sun.star.ucb.InsertCommandArgument')
#        commands['insert'] = getCommandInfo('insert', 'com.sun.star.ucb.InsertCommandArgument2')
        commands['delete'] = getCommandInfo('delete', 'boolean')
#        commands['lock'] = getCommandInfo('lock')
#        commands['unlock'] = getCommandInfo('unlock')
        commands['close'] = getCommandInfo('close')
        return commands
        
    def _updateCommandInfo(self):
        commands = {}
        commands['insert'] = getCommandInfo('insert', 'com.sun.star.ucb.InsertCommandArgument2')
        commands['checkout'] = getCommandInfo('checkout')
        commands['cancelCheckout'] = getCommandInfo('cancelCheckout')
        commands['checkin'] = getCommandInfo('checkin', 'com.sun.star.ucb.CheckinArgument')
        commands['updateProperties'] = getCommandInfo('updateProperties', '[]com.sun.star.document.CmisProperty')
        commands['getAllVersions'] = getCommandInfo('getAllVersions', '[]com.sun.star.document.CmisVersion')
        self._commandInfo.update(commands)

    def _getPropertySetInfo(self):
        properties = {}
        bound = uno.getConstantByName('com.sun.star.beans.PropertyAttribute.BOUND')
        constrained = uno.getConstantByName('com.sun.star.beans.PropertyAttribute.CONSTRAINED')
        readonly = uno.getConstantByName('com.sun.star.beans.PropertyAttribute.READONLY')
        ro = 0 if self.getIdentifier().IsNew else readonly
        properties['ContentType'] = getProperty('ContentType', 'string', bound | ro)
        properties['MimeType'] = getProperty('MimeType', 'string', bound | readonly)
        properties['MediaType'] = getProperty('MediaType', 'string', bound | readonly)
        properties['IsDocument'] = getProperty('IsDocument', 'boolean', bound | ro)
        properties['IsFolder'] = getProperty('IsFolder', 'boolean', bound | ro)
        properties['Title'] = getProperty('Title', 'string', bound | constrained)
        properties['Size'] = getProperty('Size', 'long', bound)
        properties['DateModified'] = getProperty('DateModified', 'com.sun.star.util.DateTime', bound | ro)
        properties['DateCreated'] = getProperty('DateCreated', 'com.sun.star.util.DateTime', bound | readonly)
        properties['IsReadOnly'] = getProperty('IsReadOnly', 'boolean', bound | ro)
        properties['Loaded'] = getProperty('Loaded', 'long', bound)

        properties['BaseURI'] = getProperty('BaseURI', 'string', bound | readonly)
        properties['TargetURL'] = getProperty('TargetURL', 'string', bound | readonly)
        properties['TitleOnServer'] = getProperty('TitleOnServer', 'string', bound)

        properties['ObjectId'] = getProperty('ObjectId', 'string', bound | readonly)
        properties['CasePreservingURL'] = getProperty('CasePreservingURL', 'string', bound)
        properties['CreatableContentsInfo'] = getProperty('CreatableContentsInfo', '[]com.sun.star.ucb.ContentInfo', bound)
        
        properties['IsHidden'] = getProperty('IsHidden', 'boolean', bound | ro)
        properties['IsVolume'] = getProperty('IsVolume', 'boolean', bound | ro)
        properties['IsRemote'] = getProperty('IsRemote', 'boolean', bound | ro)
        properties['IsRemoveable'] = getProperty('IsRemoveable', 'boolean', bound | ro)
        properties['IsFloppy'] = getProperty('IsFloppy', 'boolean', bound | ro)
        properties['IsCompactDisc'] = getProperty('IsCompactDisc', 'boolean', bound | ro)
        return properties

#        properties['CanCheckIn'] = getProperty('CanCheckIn', 'boolean', bound)
#        properties['CanCancelCheckOut'] = getProperty('CanCancelCheckOut', 'boolean', bound)
#        properties['Author'] = getProperty('Author', 'string', bound)
#        properties['Keywords'] = getProperty('Keywords', 'string', bound)
#        properties['Subject'] = getProperty('Subject', 'string', bound)

    def _getCmisPropertySetInfo(self):
        properties = {}
        bound = uno.getConstantByName('com.sun.star.beans.PropertyAttribute.BOUND')
        readonly = uno.getConstantByName('com.sun.star.beans.PropertyAttribute.READONLY')
        properties['CmisProperties'] = getProperty('CmisProperties', '[]com.sun.star.document.CmisProperty', bound | readonly)
        properties['IsVersionable'] = getProperty('IsVersionable', 'boolean', bound | readonly)
        properties['CanCheckOut'] = getProperty('CanCheckOut', 'boolean', bound)
        properties['CanCheckIn'] = getProperty('CanCheckIn', 'boolean', bound)
        properties['CanCancelCheckOut'] = getProperty('CanCancelCheckOut', 'boolean', bound)
        self._propertySetInfo.update(properties)
        self._updateCommandInfo()
        return properties

    def _getCmisProperties(self):
        properties = []
        properties.append(getCmisProperty('cmis:isVersionSeriesCheckedOut', 'isVersionSeriesCheckedOut', 'boolean', True, True, False, True, (), True))
        properties.append(getCmisProperty('cmis:title', 'title', 'string', True, True, False, True, (), 'nouveau titre'))
        return tuple(properties)

#        self._propertySetInfo.update({property.Name: property})
#        reason = uno.getConstantByName('com.sun.star.beans.PropertySetInfoChange.PROPERTY_INSERTED')
#        event = getPropertySetInfoChangeEvent(self, property.Name, reason)
#        for listener in self.propertyInfoListeners:
#            listener.propertySetInfoChange(event)

    # XServiceInfo
    def supportsService(self, service):
        return g_ImplementationHelper.supportsService(g_ImplementationName, service)
    def getImplementationName(self):
        return g_ImplementationName
    def getSupportedServiceNames(self):
        return g_ImplementationHelper.getSupportedServiceNames(g_ImplementationName)


g_ImplementationHelper.addImplementation(DriveOfficeContent,                                                 # UNO object class
                                         g_ImplementationName,                                               # Implementation name
                                        (g_ImplementationName, 'com.sun.star.ucb.Content'))                  # List of implemented services
