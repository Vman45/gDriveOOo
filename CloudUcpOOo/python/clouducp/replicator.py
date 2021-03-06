#!
# -*- coding: utf_8 -*-

#from __futur__ import absolute_import

import uno
import unohelper

from com.sun.star.util import XCancellable
from com.sun.star.logging.LogLevel import INFO
from com.sun.star.logging.LogLevel import SEVERE

from unolib import KeyMap
from unolib import getDateTime
from unolib import unparseTimeStamp
from unolib import parseDateTime

from .configuration import g_sync
from .database import DataBase

from .dbinit import getDataSourceUrl
from .dbinit import createDataBase

from .dbtools import getDataSourceConnection
from .dbtools import createDataSource
from .dbtools import registerDataSource

from .logger import logMessage
from .logger import getMessage

from threading import Thread
import traceback
import time

class Replicator(unohelper.Base,
                 XCancellable,
                 Thread):
    def __init__(self, ctx, datasource, provider, users, sync):
        Thread.__init__(self)
        self.ctx = ctx
        self.DataBase = DataBase(self.ctx, datasource)
        self.Provider = provider
        self.Users = users
        self.canceled = False
        self.sync = sync
        sync.clear()
        self.error = None
        self.start()

    # XCancellable
    def cancel(self):
        self.canceled = True
        self.sync.set()
        self.join()

    def run(self):
        try:
            msg = "Replicator for Scheme: %s loading ... " % self.Provider.Scheme
            print("Replicator.run() 1 *************************************************************")
            logMessage(self.ctx, INFO, "stage 1", 'Replicator', 'run()')
            print("Replicator run() 2")
            while not self.canceled:
                self.sync.wait(g_sync)
                self._synchronize()
                self.sync.clear()
                print("replicator.run() 3")
            print("replicator.run() 4 *************************************************************")
        except Exception as e:
            msg = "Replicator run(): Error: %s - %s" % (e, traceback.print_exc())
            print(msg)

    def _synchronize(self):
        if self.Provider.isOffLine():
            msg = getMessage(self.ctx, 111)
            logMessage(self.ctx, INFO, msg, 'Replicator', '_synchronize()')
        elif not self.canceled:
            timestamp = parseDateTime()
            self._syncData(timestamp)

    def _syncData(self, timestamp):
        try:
            print("Replicator.synchronize() 1")
            results = []
            for user in self.Users.values():
                if self.canceled:
                    break
                msg = getMessage(self.ctx, 110, user.Name)
                logMessage(self.ctx, INFO, msg, 'Replicator', '_syncData()')
                if not user.Token:
                    start = self._initUser(user)
                    #start = self.DataBase.getUserTimeStamp(user.Id)
                    self._setSyncToken(user)
                else:
                    start = self.DataBase.getUserTimeStamp(user.Id)
                if user.Token:
                    results += self._pullData(user)
                    results += self._pushData(user, start)
                msg = getMessage(self.ctx, 116, user.Name)
                logMessage(self.ctx, INFO, msg, 'Replicator', '_syncData()')
            result = all(results)
            print("Replicator.synchronize() 2 %s" % result)
        except Exception as e:
            print("Replicator.synchronize() ERROR: %s - %s" % (e, traceback.print_exc()))

    def _initUser(self, user):
        # This procedure corresponds to the initial pull
        rejected, rows, page, row, start = self._updateDrive(user)
        print("Replicator._initUser() 1 %s - %s - %s - %s" % (len(rows), all(rows), page, row))
        msg = getMessage(self.ctx, 120, (page, row, len(rows)))
        logMessage(self.ctx, INFO, msg, 'Replicator', '_syncData()')
        if len(rejected):
            msg = getMessage(self.ctx, 121, len(rejected))
            logMessage(self.ctx, SEVERE, msg, 'Replicator', '_syncData()')
        for item in rejected:
            msg = getMessage(self.ctx, 122, item)
            logMessage(self.ctx, SEVERE, msg, 'Replicator', '_syncData()')
        print("Replicator._initUser() 2 %s" % (all(rows), ))
        return start

    def _pullData(self, user):
        results = []
        self._checkNewIdentifier(user)
        print("Replicator._pullData() 1")
        parameter = user.Provider.getRequestParameter('getChanges', user.MetaData)
        enumerator = user.Request.getIterator(parameter, None)
        print("Replicator._pullData() 2 %s - %s" % (enumerator.PageCount, enumerator.SyncToken))
        while enumerator.hasMoreElements():
            response = enumerator.nextElement()
            print("Replicator._pullData() 3 %s" % response)
        print("Replicator._pullData() 4 %s - %s" % (enumerator.PageCount, enumerator.SyncToken))
        return results

    def _pushData(self, user, start):
        try:
            results = []
            end = parseDateTime()
            chunk = user.Provider.Chunk
            url = user.Provider.SourceURL
            uploader = user.Request.getUploader(chunk, url, self.DataBase.callBack)
            for item in self.DataBase.getInsertedItems(user.Id, start, end):
                results.append(self._synchronizeCreatedItems(user, uploader, item))
            for item in self.DataBase.getUpdatedItems(user.Id, start, end):
                results.append(self._synchronizeUpdatedItems(user, uploader, item))
            if all(results):
                pass
                self.DataBase.updateUserTimeStamp(user.Id, end)
                print("Replicator._pushData() Created / Updated Items OK")
            return results
        except Exception as e:
            print("Replicator.synchronize() ERROR: %s - %s" % (e, traceback.print_exc()))

    def _setSyncToken(self, user):
        data = user.Provider.getToken(user.Request, user.MetaData)
        if data.IsPresent:
            token = user.Provider.getUserToken(data.Value)
            self.DataBase.updateToken(user.MetaData, token)

    def _checkNewIdentifier(self, user):
        if user.Provider.isOffLine() or not user.Provider.GenerateIds:
            return
        if self.DataBase.countIdentifier(user.Id) < min(user.Provider.IdentifierRange):
            enumerator = user.Provider.getIdentifier(user.Request, user.MetaData)
            self.DataBase.insertIdentifier(enumerator, user.Id)
        # Need to postpone the creation authorization after this verification...
        user.CanAddChild = True

    def _updateDrive(self, user):
        separator = ','
        start = parseDateTime()
        call = self.DataBase.getDriveCall(user.Id, separator, 1, start)
        roots = [user.RootId]
        rows, items, parents, page, row = self._getDriveContent(call, user, roots, separator, start)
        rows += self._filterParents(call, user.Provider, items, parents, roots, separator, start)
        rejected = self._getRejectedItems(user.Provider, parents, items)
        if row > 0:
            call.executeBatch()
        call.close()
        end = parseDateTime()
        self.DataBase.updateUserTimeStamp(user.Id, end)
        return rejected, rows, page, row, end

    def _getDriveContent(self, call, user, roots, separator, start):
        rows = []
        items = {}
        childs = []
        provider = user.Provider
        parameter = provider.getRequestParameter('getDriveContent', user.MetaData)
        enumerator = user.Request.getIterator(parameter, None)
        while enumerator.hasMoreElements():
            item = enumerator.nextElement()
            itemid = provider.getItemId(item)
            parents = provider.getItemParent(item, user.RootId)
            if all(parent in roots for parent in parents):
                roots.append(itemid)
                row = self.DataBase.setDriveCall(call, provider, item, itemid, parents, separator, start)
                rows.append(row)
            else:
                items[itemid] = item
                childs.append((itemid, parents))
        return rows, items, childs, enumerator.PageCount, enumerator.RowCount

    def _filterParents(self, call, provider, items, childs, roots, separator, start):
        i = -1
        rows = []
        while len(childs) and len(childs) != i:
            i = len(childs)
            print("replicator._filterParents() %s" % len(childs))
            for item in childs:
                itemid, parents = item
                if all(parent in roots for parent in parents):
                    roots.append(itemid)
                    row = self.DataBase.setDriveCall(call, provider, items[itemid], itemid, parents, separator, start)
                    rows.append(row)
                    childs.remove(item)
            childs.reverse()
        return rows

    def _getRejectedItems(self, provider, items, data):
        rejected = []
        for itemid, parents in items:
            title = provider.getItemTitle(data[itemid])
            rejected.append((title, itemid, ','.join(parents)))
        return rejected

    def _synchronizeCreatedItems(self, user, uploader, item):
        try:
            response = False
            mediatype = item.getValue('MediaType')
            if user.Provider.isFolder(mediatype):
                response = user.Provider.createFolder(user.Request, item)
            elif user.Provider.isLink(mediatype):
                pass
            elif user.Provider.isDocument(mediatype):
                if user.Provider.createFile(user.Request, uploader, item):
                    response = user.Provider.uploadFile(user.Request, uploader, item, True)
            msg = "ItemId - Title - MediaType: %s - %s - %s" % (item.getValue('Id'),
                                                                item.getValue('Title'),
                                                                mediatype)
            print(msg)
            #logMessage(self.ctx, INFO, msg, "Replicator", "_syncItem()")
            return response
        except Exception as e:
            msg = "ERROR: %s - %s" % (e, traceback.print_exc())
            logMessage(self.ctx, SEVERE, msg, "Replicator", "_syncItem()")

    def _synchronizeUpdatedItems(self, user, uploader, item):
        try:
            response = False
            if item.getValue('SizeUpdated'):
                response = user.Provider.uploadFile(user.Request, uploader, item, False)
            if item.getValue('TitleUpdated'):
                response = user.Provider.updateTitle(user.Request, item)
            if item.getValue('TrashedUpdated'):
                response = user.Provider.updateTrashed(user.Request, item)
            print("Replicator._synchronizeUpdatedItems() %s - %s - %s" % (item.getValue('TitleUpdated'),
                                                                          item.getValue('SizeUpdated'),
                                                                          item.getValue('TrashedUpdated')))
            return response
        except Exception as e:
            msg = "ERROR: %s - %s" % (e, traceback.print_exc())
            logMessage(self.ctx, SEVERE, msg, "Replicator", "_synchronizeUpdatedItems()")
