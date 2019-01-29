#!
# -*- coding: utf_8 -*-

import uno

from com.sun.star.ucb.ConnectionMode import ONLINE, OFFLINE

from .items import mergeJsonItemCall, mergeJsonItem
from .google import ChildGenerator, g_folder

import traceback


def isChild(connection, id, parent):
    ischild = False
    call = connection.prepareCall('CALL "isChild"(?, ?)')
    call.setString(1, id)
    call.setString(2, parent)
    result = call.executeQuery()
    if result.next():
        ischild = result.getBoolean(1)
    call.close()
    return ischild

def updateChildren(connection, session, identifier):
    merge, index = mergeJsonItemCall(connection, identifier.UserId)
    update = all(mergeJsonItem(merge, item, index) for item in ChildGenerator(session, identifier.Id))
    merge.close()
    session.close()
    return update

def getChildSelect(connection, identifier):
    try:
        # LibreOffice Columns: ['Title', 'Size', 'DateModified', 'DateCreated', 'IsFolder', 'TargetURL', 'IsHidden', 'IsVolume', 'IsRemote', 'IsRemoveable', 'IsFloppy', 'IsCompactDisc']
        # OpenOffice Columns: ['Title', 'Size', 'DateModified', 'DateCreated', 'IsFolder', 'TargetURL', 'IsHidden', 'IsVolume', 'IsRemote', 'IsRemoveable', 'IsFloppy', 'IsCompactDisc']
        index, select = 1, connection.prepareCall('CALL "selectChild"(?, ?, ?, ?, ?)')
        # select return RowCount as OUT parameter in select.getLong(index)!!!
        # Never managed to run the next line:
        # select.ResultSetType = uno.getConstantByName('com.sun.star.sdbc.ResultSetType.SCROLL_INSENSITIVE')
        # selectChild(IN ID VARCHAR(100),IN URL VARCHAR(250),IN MODE SMALLINT,OUT ROWCOUNT SMALLINT)
        select.setString(index, identifier.Id)
        index += 1
        # "TargetURL" is done by CONCAT(uri,id,'/',title)... The root uri already ends with a '/' ...
        uri = identifier.getContentIdentifier()
        select.setString(index, uri if uri.endswith('/') else '%s/' % uri)
        index += 1
        # "IsFolder" is done by comparing MimeType with g_folder 'application/vnd.google-apps.folder' ...
        select.setString(index, g_folder)
        index += 1
        select.setLong(index, identifier.ConnectionMode)
        index += 1
        return index, select
    except Exception as e:
        print("children.getChildSelect().Error: %s - %s" % (e, traceback.print_exc()))
