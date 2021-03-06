#!
# -*- coding: utf_8 -*-

from com.sun.star.sdbc import SQLException
from com.sun.star.logging.LogLevel import INFO
from com.sun.star.logging.LogLevel import SEVERE

from unolib import KeyMap
from unolib import createService
from unolib import getResourceLocation
from unolib import getSimpleFile

from .dbconfig import g_path
from .dbconfig import g_version
from .dbconfig import g_role

from .dbtools import registerDataSource
from .dbtools import executeQueries
from .dbtools import executeSqlQueries
from .dbtools import getDataSourceConnection
from .dbtools import getDataSourceCall
from .dbtools import getSequenceFromResult
from .dbtools import getKeyMapFromResult
from .dbtools import createDataSource
from .dbtools import checkDataBase
from .dbtools import createStaticTable

from .dbqueries import getSqlQuery

import traceback


def getDataSourceUrl(ctx, dbname, plugin, register):
    error = None
    print("dbinit.getDataSourceUrl() 1")
    url = getResourceLocation(ctx, plugin, g_path)
    odb = '%s/%s.odb' % (url, dbname)
    print("dbinit.getDataSourceUrl() 2")
    dbcontext = createService(ctx, 'com.sun.star.sdb.DatabaseContext')
    print("dbinit.getDataSourceUrl() 3")
    if not getSimpleFile(ctx).exists(odb):
        print("dbinit.getDataSourceUrl() 4")
        datasource = createDataSource(dbcontext, url, dbname)
        error = createDataBase(ctx, datasource, url, dbname)
        print("dbinit.getDataSourceUrl() 5 %s" % error)
        if error is None:
            datasource.DatabaseDocument.storeAsURL(odb, ())
    if error is None and register:
        registerDataSource(dbcontext, dbname, odb)
    return url, error

def createDataBase(ctx, connection):
    print("dbinit.createDataBase() 1")
    version, error = checkDataBase(ctx, connection)
    print("dbinit.createDataBase() 2")
    if error is None:
        print("dbinit.createDataBase() 3")
        statement = connection.createStatement()
        createStaticTable(statement, getStaticTables(), True)
        tables, statements = getTablesAndStatements(statement, version)
        executeSqlQueries(statement, tables)
        executeQueries(statement, getViews())
    print("dbinit.createDataBase() 4")
    return error

def createDataBase1(ctx, datasource, url, dbname):
    error = None
    try:
        print("dbinit.createDataBase() 1")
        connection = datasource.getConnection('', '')
    except SQLException as e:
        error = e
    else:
        print("dbinit.createDataBase() 2")
        version, error = checkDataBase(ctx, connection)
        print("dbinit.createDataBase() 3")
        if error is None:
            print("dbinit.createDataBase() 4")
            statement = connection.createStatement()
            createStaticTable(statement, getStaticTables(), True)
            tables, statements = getTablesAndStatements(statement, version)
            executeSqlQueries(statement, tables)
            executeQueries(statement, getViews())
        connection.close()
        connection.dispose()
        print("dbinit.createDataBase() 5")
    return error

def getTablesAndStatements(statement, version=g_version):
    tables = []
    statements = []
    call = getDataSourceCall(statement.getConnection(), 'getTables')
    for table in getSequenceFromResult(statement.executeQuery(getSqlQuery('getTableName'))):
        view = False
        versioned = False
        columns = []
        primary = []
        unique = []
        constraint = []
        call.setString(1, table)
        result = call.executeQuery()
        while result.next():
            data = getKeyMapFromResult(result, KeyMap())
            view = data.getValue('View')
            versioned = data.getValue('Versioned')
            column = data.getValue('Column')
            definition = '"%s"' % column
            definition += ' %s' % data.getValue('Type')
            lenght = data.getValue('Lenght')
            definition += '(%s)' % lenght if lenght else ''
            default = data.getValue('Default')
            definition += ' DEFAULT %s' % default if default else ''
            options = data.getValue('Options')
            definition += ' %s' % options if options else ''
            columns.append(definition)
            if data.getValue('Primary'):
                primary.append('"%s"' % column)
            if data.getValue('Unique'):
                unique.append({'Table': table, 'Column': column})
            if data.getValue('ForeignTable') and data.getValue('ForeignColumn'):
                constraint.append({'Table': table,
                                   'Column': column,
                                   'ForeignTable': data.getValue('ForeignTable'),
                                   'ForeignColumn': data.getValue('ForeignColumn')})
        if primary:
            columns.append(getSqlQuery('getPrimayKey', primary))
        for format in unique:
            columns.append(getSqlQuery('getUniqueConstraint', format))
        for format in constraint:
            columns.append(getSqlQuery('getForeignConstraint', format))
        if version >= '2.5.0' and versioned:
            columns.append(getSqlQuery('getPeriodColumns'))
        format = (table, ','.join(columns))
        query = getSqlQuery('createTable', format)
        if version >= '2.5.0' and versioned:
            query += getSqlQuery('getSystemVersioning')
        tables.append(query)
        if view:
            typed = False
            for format in constraint:
                if format['Column'] == 'Type':
                    typed = True
                    break
            format = {'Table': table}
            if typed:
                merge = getSqlQuery('createTypedDataMerge', format)
            else:
                merge = getSqlQuery('createUnTypedDataMerge', format)
            statements.append(merge)
    call.close()
    return tables, statements

def getStaticTables():
    tables = ('Tables',
              'Columns',
              'TableColumn',
              'Settings')
    return tables

def getQueries():
    return (('createRole',{'Role': g_role}),
            ('grantPrivilege',{'Privilege':'SELECT','Table': 'Users', 'Role': g_role}),
            ('grantPrivilege',{'Privilege':'SELECT,DELETE','Table': 'Identifiers', 'Role': g_role}),
            ('grantPrivilege',{'Privilege':'SELECT,INSERT,UPDATE,DELETE','Table': 'Items', 'Role': g_role}),
            ('grantPrivilege',{'Privilege':'SELECT,INSERT,UPDATE,DELETE','Table': 'Parents', 'Role': g_role}),
            ('grantPrivilege',{'Privilege':'SELECT,INSERT,UPDATE,DELETE','Table': 'Capabilities', 'Role': g_role}),

            ('createItemView',{'Role': g_role}),
            ('createChildView',{'Role': g_role}),
            ('createSyncView',{}),
            ('createTwinView',{'Role': g_role}),
            ('createUriView',{'Role': g_role}),
            ('createTileView',{'Role': g_role}),
            ('createChildrenView',{'Role': g_role}),

            ('createGetIdentifier',{'Role': g_role}),

            ('createMergeItem',{'Role': g_role}),
            ('createInsertItem',{'Role': g_role}),
            ('createInsertAndSelectItem',{'Role': g_role}))

#            ('createGetItem1',{'Role': g_role}),
#            ('createGetChildren1',{'Role': g_role}),
#            ('createUpdateTitle',{'Role': g_role}),
#            ('createUpdateSize',{'Role': g_role}),
#            ('createUpdateTrashed',{'Role': g_role}),
