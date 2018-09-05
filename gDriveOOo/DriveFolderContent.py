#!
# -*- coding: utf_8 -*-

import uno
import unohelper

from com.sun.star.awt import XCallback
from com.sun.star.beans import XPropertyContainer
from com.sun.star.container import XChild
from com.sun.star.lang import XServiceInfo, NoSupportException
from com.sun.star.ucb import XContent, XCommandProcessor2, XContentCreator, IllegalIdentifierException
from com.sun.star.ucb import InteractiveBadTransferURLException
from com.sun.star.ucb.ConnectionMode import ONLINE, OFFLINE

from gdrive import Component, Initialization, CommandInfo, PropertySetInfo, DynamicResultSet, ContentIdentifier
from gdrive import PropertiesChangeNotifier, PropertySetInfoChangeNotifier, CommandInfoChangeNotifier, Row
from gdrive import getDbConnection, propertyChange, getChildSelect, parseDateTime, getPropertiesValues, getLogger

from gdrive import updateChildren, createService, getSimpleFile, getResourceLocation, isChild
from gdrive import getUcb, getCommandInfo, getProperty, getContentInfo, setContentProperties
from gdrive import getContent, getContentEvent, setPropertiesValues
from gdrive import getUcp, createNewContent, uploadItem

import requests
import traceback

# pythonloader looks for a static g_ImplementationHelper variable
g_ImplementationHelper = unohelper.ImplementationHelper()
g_ImplementationName = 'com.gmail.prrvchr.extensions.gDriveOOo.DriveFolderContent'


class DriveFolderContent(unohelper.Base, XServiceInfo, Component, Initialization, PropertiesChangeNotifier,
                         XContent, XCommandProcessor2, XContentCreator, XChild, XCallback,
                         PropertySetInfoChangeNotifier, XPropertyContainer, CommandInfoChangeNotifier):
    def __init__(self, ctx, *namedvalues):
        try:
            self.ctx = ctx
            self.Logger = getLogger(self.ctx)
            level = uno.getConstantByName("com.sun.star.logging.LogLevel.INFO")
            msg = "DriveFolderContent loading ..."
            self.Logger.logp(level, "DriveFolderContent", "__init__()", msg)
            self.Identifier = None

            self.ContentType = 'application/vnd.google-apps.folder'
            self.IsFolder = True
            self.IsDocument = False
            self.Name = 'Sans Nom'
            
            self.MediaType = 'application/vnd.google-apps.folder'
            self.Size = 0
            self.DateModified = parseDateTime()
            self.DateCreated = parseDateTime()
            self._IsRead = False
            self.WhoWrite = ''
            self.CanRename = False
            self.IsVersionable = False
            self.CreatableContentsInfo = self._getCreatableContentsInfo()

            self.IsHidden = False
            self.IsVolume = False
            self.IsRemote = False
            self.IsRemoveable = False
            self.IsFloppy = False
            self.IsCompactDisc = False

            self._commandInfo = self._getCommandInfo()
            self._propertySetInfo = self._getPropertySetInfo()
            self.listeners = []
            self.contentListeners = []
            self.propertiesListener = {}
            self.propertyInfoListeners = []
            self.commandInfoListeners = []
            
            self.Statement = None
            self.initialize(namedvalues)
            msg = "DriveFolderContent loading Uri: %s ... Done" % self.Identifier.getContentIdentifier()
            self.Logger.logp(level, "DriveFolderContent", "__init__()", msg)
            print(msg)
        except Exception as e:
            print("DriveFolderContent.__init__().Error: %s - %e" % (e, traceback.print_exc()))

    @property
    def Id(self):
        return self.Identifier.Id
    @Id.setter
    def Id(self, id):
        propertyChange(self, 'Id', self.Id, id)
    @property
    def Title(self):
        return self.Name
    @Title.setter
    def Title(self, title):
        propertyChange(self, 'Name', self.Name, title)
        self.Name = title
    @property
    def IsRead(self):
        return self._IsRead
    @IsRead.setter
    def IsRead(self, isread):
        propertyChange(self, 'IsRead', self._IsRead, isread)
        self._IsRead = isread
    @property
    def WhoWrite(self):
        return self._WhoWrite
    @WhoWrite.setter
    def WhoWrite(self, whowrite):
        propertyChange(self, 'WhoWrite', self._WhoWrite, whowrite)
        self._WhoWrite = whowrite

    # XPropertyContainer
    def addProperty(self, name, attribute, default):
        print("DriveFolderContent.addProperty()")
    def removeProperty(self, name):
        print("DriveFolderContent.removeProperty()")

    # XCallback
    def notify(self, data):
        for listener in self.contentListeners:
            listener.contentEvent(data)

    # XContentCreator
    def queryCreatableContentsInfo(self):
        print("DriveFolderContent.queryCreatableContentsInfo():*************************")
        return self.CreatableContentsInfo
    def createNewContent(self, contentinfo):
        print("DriveFolderContent.createNewContent():************************* %s" % contentinfo)
        return createNewContent(self.ctx, self.Statement, self.Identifier.getContentIdentifier(), contentinfo)

    # XChild
    def getParent(self):
        print("DriveFolderContent.getParent()")
        identifier = self.Identifier.getParent()
        return getContent(self.ctx, identifier)
    def setParent(self, parent):
        print("DriveFolderContent.setParent()")
        raise NoSupportException('Parent can not be set', self)

    # XContent
    def getIdentifier(self):
        return self.Identifier
    def getContentType(self):
        return self.ContentType
    def addContentEventListener(self, listener):
        #print("DriveFolderContent.addContentEventListener():*************************")
        self.contentListeners.append(listener)
    def removeContentEventListener(self, listener):
        #print("DriveFolderContent.removeContentEventListener():*************************")
        if listener in self.contentListeners:
            self.contentListeners.remove(listener)

    # XCommandProcessor2
    def createCommandIdentifier(self):
        print("DriveFolderContent.createCommandIdentifier(): **********************")
        return 0
    def execute(self, command, id, environment):
        print("DriveFolderContent.execute(): %s" % command.Name)
        if command.Name == 'getCommandInfo':
            return CommandInfo(self._commandInfo)
        elif command.Name == 'getPropertySetInfo':
            return PropertySetInfo(self._propertySetInfo)
        elif command.Name == 'getPropertyValues':
            namedvalues = getPropertiesValues(self, command.Argument,self.Logger)
            return Row(namedvalues)
        elif command.Name == 'setPropertyValues':
            return setPropertiesValues(self, command.Argument, self.Logger)
        elif command.Name == 'open':
            scheme = self.Identifier.getContentProviderScheme()
            connection = self.Statement.getConnection()
            mode = self.Identifier.ConnectionMode
            if mode == ONLINE and not self.IsRead:
                self.IsRead = updateChildren(self.ctx, connection, scheme, self.Identifier.UserName, self.Id)
            # Not Used: command.Argument.Properties - Implement me ;-)
            index, select = getChildSelect(connection, mode, self.Id, self.Identifier.getContentIdentifier(), False)
            return DynamicResultSet(self.ctx, scheme, select, index)
        elif command.Name == 'createNewContent':
            print("DriveFolderContent.execute(): createNewContent %s" % command.Argument)
            return createNewContent(self.ctx, self.Statement, self.Identifier.getContentIdentifier(), command.Argument)
        elif command.Name == 'insert':
            print("DriveFolderContent.execute() insert")
            #identifier = self.Identifier.getParent()
            #action = uno.getConstantByName('com.sun.star.ucb.ContentAction.INSERTED')
            #event = getContentEvent(action, self, identifier)
            self.WhoWrite = self.Identifier.UserName
            ucp = getUcp(self.ctx, self.Identifier.getContentIdentifier())
            self.addPropertiesChangeListener(('Id', 'WhoWrite', 'IsRead', 'Name', 'Size'), ucp)
            self.Id = self.Id
            if self.Identifier.ConnectionMode == ONLINE:
                pass
        elif command.Name == 'delete':
            print("DriveFolderContent.execute(): delete")
        elif command.Name == 'transfer':
            # Transfer command is only used for existing document (File Save)
            id = command.Argument.NewTitle
            source = command.Argument.SourceURL
            print("DriveFolderContent.execute(): transfer: %s - %s" % (source, id))
            if not isChild(self.Statement.getConnection(), id, self.Id):
                # For new document (File Save As) we use command: createNewContent and Insert
                print("DriveFolderContent.execute(): transfer copy: %s - %s" % (source, id))
                raise InteractiveBadTransferURLException("Couln't handle Url: %s" % source, self)
            print("DriveFolderContent.execute(): transfer: %s - %s" % (source, id))
            sf = getSimpleFile(self.ctx)
            if sf.exists(source):
                target = getResourceLocation(self.ctx, '%s/%s' % (self.Identifier.getContentProviderScheme(), id))
                inputstream = sf.openFileRead(source)
                sf.writeFile(target, inputstream)
                inputstream.closeInput()
                ucb = getUcb(self.ctx)
                # Folder Uri end whith it's Id: ie: 'scheme://authority/.../parentId/folderId'
                identifier = ucb.createContentIdentifier('%s/%s' % (self.Identifier.getContentIdentifier(), id))
                content = ucb.queryContent(identifier)
                size = sf.getSize(target)
                properties = {'Size': size, 'WhoWrite': self.Identifier.UserName}
                setContentProperties(content, properties)
                row = getContentProperties(content, ('Name', 'MediaType'))
                if self.Identifier.ConnectionMode == ONLINE:
                    inputstream = sf.openFileRead(target)
                    uploadItem(self.ctx, inputstream, identifier, row.getString(1), size, row.getString(2))                
                print("DriveFolderContent.execute(): transfer: Fin")
                if command.Argument.MoveData:
                    pass #must delete object
        elif command.Name == 'close':
            print("DriveFolderContent.execute(): close")
        elif command.Name == 'flush':
            print("DriveFolderContent.execute(): flush")
        #except Exception as e:
        #    print("DriveFolderContent.execute().Error: %s - %e" % (e, traceback.print_exc()))

    def abort(self, id):
        pass
    def releaseCommandIdentifier(self, id):
        pass

    def _getCommandInfo(self):
        commands = {}
        commands['getCommandInfo'] = getCommandInfo('getCommandInfo')
        commands['getPropertySetInfo'] = getCommandInfo('getPropertySetInfo')
        commands['getPropertyValues'] = getCommandInfo('getPropertyValues', '[]com.sun.star.beans.Property')
        commands['setPropertyValues'] = getCommandInfo('setPropertyValues', '[]com.sun.star.beans.PropertyValue')
        commands['open'] = getCommandInfo('open', 'com.sun.star.ucb.OpenCommandArgument2')
        commands['createNewContent'] = getCommandInfo('createNewContent', 'com.sun.star.ucb.ContentInfo')
        commands['insert'] = getCommandInfo('insert', 'com.sun.star.ucb.InsertCommandArgument')
#        commands['insert'] = getCommandInfo('insert', 'com.sun.star.ucb.InsertCommandArgument2')
        commands['delete'] = getCommandInfo('delete', 'boolean')
        commands['transfer'] = getCommandInfo('transfer', 'com.sun.star.ucb.TransferInfo')
        commands['close'] = getCommandInfo('close')
        commands['flush'] = getCommandInfo('flush')
        return commands

    def _getPropertySetInfo(self):
        properties = {}
        bound = uno.getConstantByName('com.sun.star.beans.PropertyAttribute.BOUND')
        readonly = uno.getConstantByName('com.sun.star.beans.PropertyAttribute.READONLY')
        transient = uno.getConstantByName('com.sun.star.beans.PropertyAttribute.TRANSIENT')
        properties['Id'] = getProperty('Id', 'string', bound | readonly)
#        properties['ParentsId'] = getProperty('ParentsId', '[]string', bound | readonly)
        properties['ContentType'] = getProperty('ContentType', 'string', bound | readonly)
        properties['MediaType'] = getProperty('MediaType', 'string', bound | readonly)
        properties['IsDocument'] = getProperty('IsDocument', 'boolean', bound | readonly)
        properties['IsFolder'] = getProperty('IsFolder', 'boolean', bound | readonly)
        properties['Title'] = getProperty('Title', 'string', bound)
        properties['Size'] = getProperty('Size', 'long', bound | readonly)
        properties['DateModified'] = getProperty('DateModified', 'com.sun.star.util.DateTime', bound | readonly)
        properties['DateCreated'] = getProperty('DateCreated', 'com.sun.star.util.DateTime', bound | readonly)
        properties['IsRead'] = getProperty('IsRead', 'boolean', bound)
        properties['CreatableContentsInfo'] = getProperty('CreatableContentsInfo', '[]com.sun.star.ucb.ContentInfo', bound | readonly)

        properties['IsHidden'] = getProperty('IsHidden', 'boolean', bound | readonly)
        properties['IsVolume'] = getProperty('IsVolume', 'boolean', bound | readonly)
        properties['IsRemote'] = getProperty('IsRemote', 'boolean', bound | readonly)
        properties['IsRemoveable'] = getProperty('IsRemoveable', 'boolean', bound | readonly)
        properties['IsFloppy'] = getProperty('IsFloppy', 'boolean', bound | readonly)
        properties['IsCompactDisc'] = getProperty('IsCompactDisc', 'boolean', bound | readonly)
        return properties

    def _getCreatableContentsInfo(self):
        bound = uno.getConstantByName('com.sun.star.beans.PropertyAttribute.BOUND')
        document = uno.getConstantByName('com.sun.star.ucb.ContentInfoAttribute.KIND_DOCUMENT')
        folder = uno.getConstantByName('com.sun.star.ucb.ContentInfoAttribute.KIND_FOLDER')
        foldertype = 'application/vnd.google-apps.folder'
        documenttype = 'application/vnd.oasis.opendocument'
        properties = (getProperty('Title', 'string', bound), )
        content = (getContentInfo(foldertype, folder, properties), getContentInfo(documenttype, document, properties))
        return content


    # XServiceInfo
    def supportsService(self, service):
        return g_ImplementationHelper.supportsService(g_ImplementationName, service)
    def getImplementationName(self):
        return g_ImplementationName
    def getSupportedServiceNames(self):
        return g_ImplementationHelper.getSupportedServiceNames(g_ImplementationName)


g_ImplementationHelper.addImplementation(DriveFolderContent,                                                 # UNO object class
                                         g_ImplementationName,                                               # Implementation name
                                        (g_ImplementationName, 'com.sun.star.ucb.Content'))                  # List of implemented services
