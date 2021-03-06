#!
# -*- coding: utf_8 -*-

import uno
import unohelper

from com.sun.star.lang import XEventListener
from com.sun.star.logging.LogLevel import INFO
from com.sun.star.logging.LogLevel import SEVERE
from com.sun.star.sdb.CommandType import QUERY
from com.sun.star.ucb import XRestDataBase
from com.sun.star.ucb.ConnectionMode import ONLINE
from com.sun.star.ucb.RestDataSourceSyncMode import SYNC_RETRIEVED
from com.sun.star.ucb.RestDataSourceSyncMode import SYNC_CREATED
from com.sun.star.ucb.RestDataSourceSyncMode import SYNC_FOLDER
from com.sun.star.ucb.RestDataSourceSyncMode import SYNC_FILE
from com.sun.star.ucb.RestDataSourceSyncMode import SYNC_RENAMED
from com.sun.star.ucb.RestDataSourceSyncMode import SYNC_REWRITED
from com.sun.star.ucb.RestDataSourceSyncMode import SYNC_TRASHED

from unolib import KeyMap
from unolib import g_oauth2
from unolib import createService
from unolib import getDateTime
from unolib import parseDateTime
from unolib import getResourceLocation

from .configuration import g_admin

from .dbqueries import getSqlQuery
from .dbconfig import g_role

from .dbtools import checkDataBase
from .dbtools import createStaticTable
from .dbtools import executeQueries
from .dbtools import executeSqlQueries
from .dbtools import getDataSourceCall

from .dbinit import getStaticTables
from .dbinit import getQueries
from .dbinit import getTablesAndStatements

from .dbtools import getDataBaseConnection
from .dbtools import getDataSourceConnection
from .dbtools import getKeyMapFromResult
from .dbtools import getSequenceFromResult
from .dbtools import getSqlException

from .logger import logMessage
from .logger import getMessage

from collections import OrderedDict
import traceback


class DataBase(unohelper.Base,
               XRestDataBase):
    def __init__(self, ctx, datasource, name='', password='', sync=None):
        self.ctx = ctx
        self._statement = datasource.getConnection(name, password).createStatement()
        self.sync = sync

    @property
    def Connection(self):
        return self._statement.getConnection()

# Procedures called by the DataSource
    def createDataBase(self):
        version, error = checkDataBase(self.ctx, self.Connection)
        print("DataBase.createDataBase() Hsqldb Version: %s" % version)
        if error is None:
            createStaticTable(self._statement, getStaticTables(), True)
            tables, statements = getTablesAndStatements(self._statement, version)
            executeSqlQueries(self._statement, tables)
            self._executeQueries(getQueries())
        return error

    def _executeQueries(self, queries):
        for name, format in queries:
            query = getSqlQuery(name, format)
            print("DataBase._executeQueries() %s" % query)
            self._statement.executeQuery(query)

    def storeDataBase(self, url):
        self._statement.getConnection().getParent().DatabaseDocument.storeAsURL(url, ())

    def addCloseListener(self, listener):
        self.Connection.Parent.DatabaseDocument.addCloseListener(listener)

    def shutdownDataBase(self, compact=False):
        if compact:
            query = getSqlQuery('shutdownCompact')
        else:
            query = getSqlQuery('shutdown')
        self._statement.execute(query)

    def createUser(self, user, password):
        name, password = user.getCredential(password)
        format = {'User': name, 'Password': password, 'Role': g_role, 'Admin': g_admin}
        sql = getSqlQuery('createUser', format)
        status = self._statement.executeUpdate(sql)
        sql = getSqlQuery('grantRole', format)
        status += self._statement.executeUpdate(sql)
        return status == 0

    def selectUser(self, name):
        user = None
        select = self._getCall('getUser')
        select.setString(1, name)
        result = select.executeQuery()
        if result.next():
            user = getKeyMapFromResult(result)
        select.close()
        return user

    def insertUser(self, provider, user, root):
        userid = provider.getUserId(user)
        username = provider.getUserName(user)
        displayname = provider.getUserDisplayName(user)
        rootid = provider.getRootId(root)
        rootname = provider.getRootTitle(root)
        timestamp = parseDateTime()
        insert = self._getCall('insertUser')
        insert.setString(1, username)
        insert.setString(2, displayname)
        insert.setString(3, rootid)
        insert.setTimestamp(4, timestamp)
        insert.setString(5, userid)
        insert.execute()
        insert.close()
        self._mergeRoot(provider, userid, rootid, rootname, root, timestamp)
        data = KeyMap()
        data.insertValue('UserId', userid)
        data.insertValue('UserName', username)
        data.insertValue('RootId', rootid)
        data.insertValue('RootName', rootname)
        data.insertValue('Token', '')
        return data

    def getContentType(self):
        call = self._getCall('getContentType')
        result = call.executeQuery()
        if result.next():
            folder = result.getString(1)
            link = result.getString(2)
        call.close()
        return folder, link

# Procedures called by the User
    def selectItem(self, user, identifier):
        item = None
        select = self._getCall('getItem1')
        select.setString(1, user.getValue('UserId'))
        select.setString(2, identifier.getValue('Id'))
        result = select.executeQuery()
        if result.next():
            item = getKeyMapFromResult(result)
        select.close()
        return item

    def insertAndSelectItem(self, user, data):
        item = None
        separator = ','
        timestamp = parseDateTime()
        call = self._getCall('insertAndSelectItem')
        call.setString(1, user.Id)
        call.setString(2, separator)
        call.setLong(3, 0)
        call.setTimestamp(4, timestamp)
        id = user.Provider.getItemId(data)
        parents = user.Provider.getItemParent(data, user.RootId)
        self._mergeItem(call, user.Provider, data, id, parents, separator, timestamp)
        result = call.executeQuery()
        if result.next():
            item = getKeyMapFromResult(result)
        call.close()
        return item

    def updateFolderContent(self, user, content):
        rows = []
        separator = ','
        timestamp = parseDateTime()
        call = self._getCall('mergeItem')
        call.setString(1, user.Id)
        call.setString(2, separator)
        call.setLong(3, 0)
        call.setTimestamp(4, timestamp)
        enumerator = user.Provider.getFolderContent(user.Request, content)
        while enumerator.hasMoreElements():
            item = enumerator.nextElement()
            id = user.Provider.getItemId(item)
            parents = user.Provider.getItemParent(item, user.RootId)
            rows.append(self._mergeItem(call, user.Provider, item, id, parents, separator, timestamp))
            call.addBatch()
        if enumerator.RowCount > 0:
            call.executeBatch()
        call.close()
        print("DataBase._updateFolderContent() %s - %s" % (all(rows), len(rows)))
        return all(rows)

    def getChildren(self, userid, itemid, url, mode):
        #TODO: Can't have a ResultSet of type SCROLL_INSENSITIVE with a Procedure,
        #TODO: as a workaround we use a simple quey...
        select = self._getCall('getChildren')
        scroll = 'com.sun.star.sdbc.ResultSetType.SCROLL_INSENSITIVE'
        select.ResultSetType = uno.getConstantByName(scroll)
        # OpenOffice / LibreOffice Columns:
        #    ['Title', 'Size', 'DateModified', 'DateCreated', 'IsFolder', 'TargetURL', 'IsHidden',
        #    'IsVolume', 'IsRemote', 'IsRemoveable', 'IsFloppy', 'IsCompactDisc']
        # "TargetURL" is done by:
        #    CONCAT(identifier.getContentIdentifier(), Uri) for File and Foder
        select.setString(1, url)
        select.setString(2, userid)
        select.setString(3, itemid)
        select.setShort(4, mode)
        return select

    def updateLoaded(self, userid, itemid, value, default):
        update = self._getCall('updateLoaded')
        update.setLong(1, value)
        update.setString(2, itemid)
        row = update.executeUpdate()
        update.close()
        return default if row != 1 else value

    def getIdentifier(self, userid, rootid, uripath):
        call = self._getCall('getIdentifier')
        call.setString(1, userid)
        call.setString(2, rootid)
        call.setString(3, uripath)
        print("DataBase.getIdentifier() %s - %s - %s" % (userid, rootid, uripath))
        call.setString(4, '/')
        call.execute()
        itemid = call.getString(5)
        parentid = call.getString(6)
        path = call.getString(7)
        call.close()
        return itemid, parentid, path

    def getNewIdentifier(self, userid):
        identifier = ''
        select = self._getCall('getNewIdentifier')
        select.setString(1, userid)
        result = select.executeQuery()
        if result.next():
            identifier = result.getString(1)
        select.close()
        return identifier

    def updateContent(self, userid, itemid, property, value):
        try:
            updated = False
            if property == 'Title':
                update = self._getCall('updateTitle')
                update.setString(1, value)
                update.setString(2, itemid)
                updated = update.execute() == 0
                update.close()
            elif property == 'Size':
                update = self._getCall('updateSize')
                update.setLong(1, value)
                update.setString(2, itemid)
                updated = update.execute() == 0
                update.close()
            elif property == 'Trashed':
                update = self._getCall('updateTrashed')
                update.setBoolean(1, value)
                update.setString(2, itemid)
                updated = update.execute() == 0
                update.close()
            if updated:
                # TODO: I cannot use a procedure performing the two UPDATE 
                # TODO: without the system versioning malfunctioning...
                # TODO: As a workaround I use two successive UPDATE queries
                timestamp = parseDateTime()
                update = self._getCall('updateCapabilities')
                update.setTimestamp(1, timestamp)
                update.setString(2, userid)
                update.setString(3, itemid)
                update.execute()
                update.close()
                self.sync.set()
                print("DataBase.updateContent() OK")
        except Exception as e:
            print("DataBase.updateContent().Error: %s - %s" % (e, traceback.print_exc()))

    def getItem(self, userid, itemid):
        #TODO: Can't have a simple SELECT ResultSet with a Procedure,
        #TODO: the malfunction is rather bizard: it always returns the same result
        #TODO: as a workaround we use a simple quey...
        item = None
        select = self._getCall('getItem')
        select.setString(1, userid)
        select.setString(2, itemid)
        result = select.executeQuery()
        if result.next():
            item = getKeyMapFromResult(result)
        select.close()
        return item

    def insertNewContent(self, userid, itemid, parentid, content, timestamp):
        call = self._getCall('insertItem')
        call.setString(1, userid)
        call.setString(2, ',')
        call.setLong(3, 1)
        call.setTimestamp(4, timestamp)
        call.setString(5, itemid)
        call.setString(6, content.getValue("Title"))
        call.setTimestamp(7, content.getValue('DateCreated'))
        call.setTimestamp(8, content.getValue('DateModified'))
        call.setString(9, content.getValue('MediaType'))
        call.setLong(10, content.getValue('Size'))
        call.setBoolean(11, content.getValue('Trashed'))
        call.setBoolean(12, content.getValue('CanAddChild'))
        call.setBoolean(13, content.getValue('CanRename'))
        call.setBoolean(14, content.getValue('IsReadOnly'))
        call.setBoolean(15, content.getValue('IsVersionable'))
        call.setString(16, parentid)
        result = call.execute() == 0
        call.close()
        if result:
            # Start Replicator for pushing changes…
            self.sync.set()
        return result

    def deleteNewIdentifier(self, userid, itemid):
        call = self._getCall('deleteNewIdentifier')
        call.setString(1, userid)
        call.setString(2, itemid)
        call.executeUpdate()
        call.close()

    def countChildTitle(self, userid, parentid, title):
        count = 1
        call = self._getCall('countChildTitle')
        call.setString(1, userid)
        call.setString(2, parentid)
        call.setString(3, title)
        result = call.executeQuery()
        if result.next():
            count = result.getLong(1)
        call.close()
        return count

    def getChildId(self, userid, parentid, title):
        id = None
        call = self._getCall('getChildId')
        call.setString(1, userid)
        call.setString(2, parentid)
        call.setString(3, title)
        result = call.executeQuery()
        if result.next():
            id = result.getString(1)
        call.close()
        return id

    def callBack(self, provider, item, response):
        if response.IsPresent:
            self._updateSync(provider, item, response.Value)

    def _updateSync(self, provider, item, response):
        oldid = item.getValue('ItemId')
        newid = provider.getResponseId(response, oldid)
        oldname = item.getValue('Title')
        newname = provider.getResponseTitle(response, oldname)
        delete = self._getCall('deleteSyncMode')
        delete.setLong(1, item.getValue('SyncId'))
        row = delete.executeUpdate()
        msg = "execute deleteSyncMode OldId: %s - NewId: %s - Row: %s" % (oldid, newid, row)
        logMessage(self.ctx, INFO, msg, "DataSource", "updateSync")
        delete.close()
        if row and newid != oldid:
            update = self._getCall('updateItemId')
            update.setString(1, newid)
            update.setString(2, oldid)
            row = update.executeUpdate()
            msg = "execute updateItemId OldId: %s - NewId: %s - Row: %s" % (oldid, newid, row)
            logMessage(self.ctx, INFO, msg, "DataSource", "updateSync")
            update.close()
        return '' if row != 1 else newid

# Procedures called by the Replicator
    # Synchronization pull token update procedure
    def updateToken(self, user, token):
        update = self._getCall('updateToken')
        update.setString(1, token)
        update.setString(2, user.getValue('UserId'))
        updated = update.executeUpdate() == 1
        update.close()
        if updated:
            user.setValue('Token', token)

    # Identifier counting procedure
    def countIdentifier(self, userid):
        count = 0
        call = self._getCall('countNewIdentifier')
        call.setString(1, userid)
        result = call.executeQuery()
        if result.next():
            count = result.getLong(1)
        call.close()
        return count

    # Identifier inserting procedure
    def insertIdentifier(self, enumerator, userid):
        result = []
        insert = self._getCall('insertIdentifier')
        insert.setString(1, userid)
        while enumerator.hasMoreElements():
            item = enumerator.nextElement()
            self._doInsert(insert, item)
        insert.executeBatch()
        insert.close()

    def _doInsert(self, insert, identifier):
        insert.setString(2, identifier)
        insert.addBatch()

    # First pull procedure: header of merge request
    def getDriveCall(self, userid, separator, loaded, timestamp):
        call = self._getCall('mergeItem')
        call.setString(1, userid)
        call.setString(2, separator)
        call.setInt(3, loaded)
        call.setTimestamp(4, timestamp)
        return call

    # First pull procedure: body of merge request
    def setDriveCall(self, call, provider, item, id, parents, separator, timestamp):
        row = self._mergeItem(call, provider, item, id, parents, separator, timestamp)
        call.addBatch()
        return row

    def updateUserTimeStamp(self, userid, timestamp):
        call = self._getCall('updateUserTimeStamp')
        call.setTimestamp(1, timestamp)
        call.setString(2, userid)
        call.executeUpdate()
        call.close()

    def getUserTimeStamp(self, userid):
        select = self._getCall('getUserTimeStamp')
        select.setString(1, userid)
        result = select.executeQuery()
        if result.next():
            timestamp = result.getTimestamp(1)
        select.close()
        return timestamp

    # Procedure to retrieve all the UPDATE in the 'Capabilities' table
    def getUpdatedItems(self, userid, start, end):
        items = []
        select = self._getCall('getUpdatedItems')
        select.setTimestamp(1, end)
        select.setTimestamp(2, start)
        select.setTimestamp(3, end)
        select.setTimestamp(4, start)
        select.setTimestamp(5, end)
        select.setTimestamp(6, start)
        select.setTimestamp(7, end)
        select.setString(8, userid)
        result = select.executeQuery()
        while result.next():
            items.append(getKeyMapFromResult(result))
        select.close()
        return items

    # Procedure to retrieve all the INSERT in the 'Capabilities' table
    def getInsertedItems(self, userid, start, end):
        items = []
        select = self._getCall('getInsertedItems')
        select.setTimestamp(1, end)
        select.setTimestamp(2, start)
        select.setString(3, userid)
        result = select.executeQuery()
        while result.next():
            items.append(getKeyMapFromResult(result))
        select.close()
        return items

    # Procedure to retrieve all the DELETE in the 'Capabilities' table
    def getDeletedItems(self, userid, start, end):
        items = []
        select = self._getCall('getDeletedItems')
        select.setTimestamp(1, start)
        select.setTimestamp(2, end)
        #select.setString(3, userid)
        result = select.executeQuery()
        while result.next():
            items.append(getKeyMapFromResult(result))
        select.close()
        msg = "getDeletedItems to Sync: %s" % (len(items), )
        print(msg)

# Procedures called internally
    def _mergeItem(self, call, provider, item, id, parents, separator, timestamp):
        call.setString(5, id)
        call.setString(6, provider.getItemTitle(item))
        call.setTimestamp(7, provider.getItemCreated(item, timestamp))
        call.setTimestamp(8, provider.getItemModified(item, timestamp))
        call.setString(9, provider.getItemMediaType(item))
        call.setLong(10, provider.getItemSize(item))
        call.setBoolean(11, provider.getItemTrashed(item))
        call.setBoolean(12, provider.getItemCanAddChild(item))
        call.setBoolean(13, provider.getItemCanRename(item))
        call.setBoolean(14, provider.getItemIsReadOnly(item))
        call.setBoolean(15, provider.getItemIsVersionable(item))
        call.setString(16, separator.join(parents))
        return 1

    def _mergeRoot(self, provider, userid, rootid, rootname, root, timestamp):
        call = self._getCall('mergeItem')
        call.setString(1, userid)
        call.setString(2, ',')
        call.setLong(3, 0)
        call.setTimestamp(4, timestamp)
        call.setString(5, rootid)
        call.setString(6, rootname)
        call.setTimestamp(7, provider.getRootCreated(root, timestamp))
        call.setTimestamp(8, provider.getRootModified(root, timestamp))
        call.setString(9, provider.getRootMediaType(root))
        call.setLong(10, provider.getRootSize(root))
        call.setBoolean(11, provider.getRootTrashed(root))
        call.setBoolean(12, provider.getRootCanAddChild(root))
        call.setBoolean(13, provider.getRootCanRename(root))
        call.setBoolean(14, provider.getRootIsReadOnly(root))
        call.setBoolean(15, provider.getRootIsVersionable(root))
        call.setString(16, '')
        call.executeUpdate()
        call.close()

    def _getCall(self, name, format=None):
        return getDataSourceCall(self.Connection, name, format)

    def _getPreparedCall(self, name):
        # TODO: cannot use: call = self.Connection.prepareCommand(name, QUERY)
        # TODO: it trow a: java.lang.IncompatibleClassChangeError
        #query = self.Connection.getQueries().getByName(name).Command
        #self._CallsPool[name] = self.Connection.prepareCall(query)
        return self.Connection.prepareCommand(name, QUERY)
