#!
# -*- coding: utf_8 -*-

import uno
import unohelper

from com.sun.star.awt import XCallback
from com.sun.star.container import XChild
from com.sun.star.lang import XServiceInfo, NoSupportException
from com.sun.star.ucb import XContent, XCommandProcessor2, XContentCreator
from com.sun.star.ucb import InteractiveBadTransferURLException, CommandAbortedException
from com.sun.star.ucb.ConnectionMode import ONLINE, OFFLINE

from gdrive import Initialization, CommandInfo, PropertySetInfo, Row, DynamicResultSet
from gdrive import PropertiesChangeNotifier, PropertySetInfoChangeNotifier, CommandInfoChangeNotifier
from gdrive import getDbConnection, getNewIdentifier, propertyChange, getChildSelect, parseDateTime, getLogger, getUcp
from gdrive import updateChildren, createService, getSimpleFile, getResourceLocation, isChild
from gdrive import getUcb, getCommandInfo, getProperty, getContentInfo, setContentProperties, createContent
from gdrive import getPropertiesValues, setPropertiesValues, getSession, g_folder
from gdrive import ACQUIRED, CREATED, RENAMED, REWRITED, TRASHED

import requests
import traceback

# pythonloader looks for a static g_ImplementationHelper variable
g_ImplementationHelper = unohelper.ImplementationHelper()
g_ImplementationName = 'com.gmail.prrvchr.extensions.gDriveOOo.DriveFolderContent'


class DriveFolderContent(unohelper.Base, XServiceInfo, Initialization, XContent, XChild, XCommandProcessor2, XContentCreator,
                         PropertiesChangeNotifier, PropertySetInfoChangeNotifier, CommandInfoChangeNotifier, XCallback):
    def __init__(self, ctx, *namedvalues):
        try:
            self.ctx = ctx

            self.Logger = getLogger(self.ctx)
            level = uno.getConstantByName("com.sun.star.logging.LogLevel.INFO")
            msg = "DriveFolderContent loading ..."
            self.Logger.logp(level, "DriveFolderContent", "__init__()", msg)

            self.Identifier = None

            self.ContentType = 'application/vnd.google-apps.folder'
            self.Name = 'Sans Nom'
            self.IsFolder = True
            self.IsDocument = False
            self.DateCreated = parseDateTime()
            self.DateModified = parseDateTime()
            self.MimeType = 'application/vnd.google-apps.folder'
            self.Size = 0
            self._Trashed = False

            self.CanAddChild = True
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

            self.initialize(namedvalues)

            self._commandInfo = self._getCommandInfo()
            self._propertySetInfo = self._getPropertySetInfo()
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
    def Scheme(self):
        return self.Identifier.getContentProviderScheme()
    @property
    def Title(self):
        return self.Name
    @Title.setter
    def Title(self, title):
        propertyChange(self, 'Name', self.Name, title)
        self.Name = title
    @property
    def Trashed(self):
        return self._Trashed
    @Trashed.setter
    def Trashed(self, trashed):
        propertyChange(self, 'Trashed', self._Trashed, trashed)
    @property
    def MediaType(self):
        return self.MimeType
    @property
    def Loaded(self):
        return self._Loaded
    @Loaded.setter
    def Loaded(self, loaded):
        propertyChange(self, 'Loaded', self._Loaded, loaded)
        self._Loaded = loaded
    @property
    def CreatableContentsInfo(self):
        content = ()
        if self.CanAddChild:
            bound = uno.getConstantByName('com.sun.star.beans.PropertyAttribute.BOUND')
            document = uno.getConstantByName('com.sun.star.ucb.ContentInfoAttribute.KIND_DOCUMENT')
            folder = uno.getConstantByName('com.sun.star.ucb.ContentInfoAttribute.KIND_FOLDER')
            foldertype = 'application/vnd.google-apps.folder'
            officetype = 'application/vnd.oasis.opendocument'
            documenttype = 'application/vnd.google-apps.document'
            properties = (getProperty('Title', 'string', bound), )
            content = (getContentInfo(foldertype, folder, properties),
                       getContentInfo(officetype, document, properties),
                       getContentInfo(documenttype, document, properties))
        return content


    # XCallback
    def notify(self, event):
        for listener in self.contentListeners:
            listener.contentEvent(event)

    # XContentCreator
    def queryCreatableContentsInfo(self):
        print("DriveFolderContent.queryCreatableContentsInfo():*************************")
        return self.CreatableContentsInfo
    def createNewContent(self, contentinfo):
        id = self.Identifier.NewIdentifier
        print("DriveFolderContent.createNewContent():\n    New Id: %s" % id)
        uri = '%s/%s/../%s' % (self.Identifier.BaseURL, id, id)
        identifier = getUcb(self.ctx).createContentIdentifier(uri)
        data = {'Identifier': identifier, 'MimeType': contentinfo.Type}
        content = createContent(self.ctx, data)
        return content

    # XChild
    def getParent(self):
        if self.Identifier.IsRoot:
            raise NoSupportException('Root Folder as no Parent', self)
        print("DriveFolderContent.getParent()")
        identifier = self.Identifier.getParent()
        return getUcb(self.ctx).queryContent(identifier)
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
            print("DriveFolderContent.execute() open 1")
            mode = self.Identifier.Mode
            if mode == ONLINE and self.Loaded == ONLINE:
                with getSession(self.ctx, self.Identifier.User.Name) as session:
                    if updateChildren(session, self.Identifier):
                        self.Loaded = OFFLINE
                    session.close()
            print("DriveFolderContent.execute() open 2")
            # Not Used: command.Argument.Properties - Implement me ;-)
            index, select = getChildSelect(self.Identifier)
            print("DriveFolderContent.execute() open 3")
            return DynamicResultSet(self.ctx, self.Identifier, select, index)
            print("DriveFolderContent.execute() open 4")
        elif command.Name == 'insert':
            print("DriveFolderContent.execute() insert")
            self.addPropertiesChangeListener(('Id', 'Name', 'Size', 'Trashed', 'Loaded'), getUcp(self.ctx))
            self.Id = CREATED
        elif command.Name == 'delete':
            print("DriveFolderContent.execute(): delete")
            self.Trashed = True
        elif command.Name == 'createNewContent':
            print("DriveFolderContent.execute(): createNewContent %s" % command.Argument)
            return self.createNewContent(command.Argument)
        elif command.Name == 'transfer':
            # Transfer command is only used for existing document (File Save)
            # NewTitle come from last segment path of "XContent.getIdentifier().getContentIdentifier()"
            id = command.Argument.NewTitle
            source = command.Argument.SourceURL
            print("DriveFolderContent.execute(): transfer 1:\n    %s - %s" % (source, id))
            if not isChild(self.Identifier.Connection, id, self.Id):
                # For new document (File Save As) we use commands:
                # createNewContent: for creating an empty new Content
                # Insert at new Content for committing change
                # For accessing this commands we must trow an "InteractiveBadTransferURLException"
                raise InteractiveBadTransferURLException("Couln't handle Url: %s" % source, self)
            print("DriveFolderContent.execute(): transfer 2:\n    transfer: %s - %s" % (source, id))
            sf = getSimpleFile(self.ctx)
            if not sf.exists(source):
                raise CommandAbortedException("Error while saving file: %s" % source, self)
            target = getResourceLocation(self.ctx, '%s/%s' % (self.Scheme, id))
            stream = sf.openFileRead(source)
            sf.writeFile(target, stream)
            stream.closeInput()
            data = {'Size': sf.getSize(target)}
            ucb = getUcb(self.ctx)
            uri = '%s/%s/../%s' % (self.Identifier.BaseURL, id, id)
            identifier = ucb.createContentIdentifier(uri)
            content = ucb.queryContent(identifier)
            setContentProperties(content, data)
            print("DriveFolderContent.execute(): transfer 3: Fin")
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
        if not self.Identifier.IsRoot:
            commands['delete'] = getCommandInfo('delete', 'boolean')
        commands['transfer'] = getCommandInfo('transfer', 'com.sun.star.ucb.TransferInfo')
        commands['close'] = getCommandInfo('close')
        commands['flush'] = getCommandInfo('flush')
        return commands

    def _getPropertySetInfo(self):
        properties = {}
        bound = uno.getConstantByName('com.sun.star.beans.PropertyAttribute.BOUND')
        constrained = uno.getConstantByName('com.sun.star.beans.PropertyAttribute.CONSTRAINED')
        readonly = uno.getConstantByName('com.sun.star.beans.PropertyAttribute.READONLY')
        transient = uno.getConstantByName('com.sun.star.beans.PropertyAttribute.TRANSIENT')
        properties['Id'] = getProperty('Id', 'string', bound | readonly)
#        properties['ParentsId'] = getProperty('ParentsId', '[]string', bound | readonly)
        properties['ContentType'] = getProperty('ContentType', 'string', bound | readonly)
        properties['MimeType'] = getProperty('MimeType', 'string', bound | readonly)
        properties['MediaType'] = getProperty('MediaType', 'string', bound | readonly)
        properties['IsDocument'] = getProperty('IsDocument', 'boolean', bound | readonly)
        properties['IsFolder'] = getProperty('IsFolder', 'boolean', bound | readonly)
        properties['Title'] = getProperty('Title', 'string', bound | constrained)
        properties['Size'] = getProperty('Size', 'long', bound | readonly)
        properties['DateModified'] = getProperty('DateModified', 'com.sun.star.util.DateTime', bound | readonly)
        properties['DateCreated'] = getProperty('DateCreated', 'com.sun.star.util.DateTime', bound | readonly)
        properties['Loaded'] = getProperty('Loaded', 'long', bound)
        properties['CreatableContentsInfo'] = getProperty('CreatableContentsInfo', '[]com.sun.star.ucb.ContentInfo', bound | readonly)

        properties['IsHidden'] = getProperty('IsHidden', 'boolean', bound | readonly)
        properties['IsVolume'] = getProperty('IsVolume', 'boolean', bound | readonly)
        properties['IsRemote'] = getProperty('IsRemote', 'boolean', bound | readonly)
        properties['IsRemoveable'] = getProperty('IsRemoveable', 'boolean', bound | readonly)
        properties['IsFloppy'] = getProperty('IsFloppy', 'boolean', bound | readonly)
        properties['IsCompactDisc'] = getProperty('IsCompactDisc', 'boolean', bound | readonly)
        return properties

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
