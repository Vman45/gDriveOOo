#!
# -*- coding: utf_8 -*-

import uno
import unohelper

from com.sun.star.sdbc import SQLException
from com.sun.star.sdbc import SQLWarning
from com.sun.star.logging.LogLevel import INFO
from com.sun.star.logging.LogLevel import SEVERE

from .keymap import KeyMap

from .unotools import getPropertyValue
from .unotools import getPropertyValueSet
from .unotools import getResourceLocation
from .unotools import getSimpleFile

from .dbqueries import getSqlQuery

from .configuration import g_protocol
from .configuration import g_path
from .configuration import g_jar
from .configuration import g_class
from .configuration import g_options
from .configuration import g_shutdown

import traceback


def getDataSourceConnection(dbcontext, url, name='', password=''):
    connection = None
    error = None
    try:
        datasource = dbcontext.getByName(url)
        connection = datasource.getConnection(name, password)
        getDataBaseVersion(connection)
    except SQLException as e:
        error = e
    print("dbtools.getDataSourceConnection()")
    return connection, error

def getDataSourceCall(connection, name, format=None):
    query = getSqlQuery(name, format)
    call = connection.prepareCall(query)
    return call

def getDataBaseVersion(connection):
    call = connection.prepareCall(getSqlQuery('getVerion'))
    result = call.executeQuery()
    while result.next():
        data = getKeyMapFromResult(result, KeyMap())
    for key in data.getKeys():
        print("dbtools.getDataBaseVersion(): %s - %s" % (key, data.getValue(key)))

def executeQueries(statement, queries):
    for query in queries:
        statement.executeQuery(getSqlQuery(query))

def getDataSourceJavaInfo(location):
    info = {}
    info['JavaDriverClass'] = g_class
    info['JavaDriverClassPath'] = '%s/%s' % (location, g_jar)
    return getPropertyValueSet(info)

def getDataSourceInfo():
    info = getDataBaseInfo()
    return getPropertyValueSet(info)

def getDataBaseInfo():
    info = {}
    info['AppendTableAliasName'] = True
    info['AutoIncrementCreation'] = 'GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY'
    info['AutoRetrievingStatement'] = 'CALL IDENTITY()'
    info['DisplayVersionColumns'] = True
    info['GeneratedValues'] = True
    info['IsAutoRetrievingEnabled'] = True
    info['ParameterNameSubstitution'] = True
    info['UseIndexDirectionKeyword'] = True
    return info

def getDriverInfo():
    info = {}
    info['AddIndexAppendix'] = True
    info['BaseDN'] = ''
    info['BooleanComparisonMode'] = 0
    info['CharSet'] = ''
    info['ColumnAliasInOrderBy'] = True
    info['CommandDefinitions'] = ''
    info['DecimalDelimiter'] = '.'

    info['EnableOuterJoinEscape'] = True
    info['EnableSQL92Check'] = False
    info['EscapeDateTime'] = True
    info['Extension'] = ''
    info['FieldDelimiter'] = ','
    info['Forms'] = ''
    info['FormsCheckRequiredFields'] = True
    info['GenerateASBeforeCorrelationName'] = False

    info['HeaderLine'] = True
    info['HostName'] = ''
    info['IgnoreCurrency'] = False
    info['IgnoreDriverPrivileges'] = True
    info['IndexAlterationServiceName'] = ''
    info['KeyAlterationServiceName'] = ''
    info['LocalSocket'] = ''

    info['MaxRowCount'] = 100
    info['Modified'] = True
    info['NamedPipe'] = ''
    info['NoNameLengthLimit'] = False
    info['PortNumber'] = 389
    info['PreferDosLikeLineEnds'] = False
    info['Reports'] = ''

    info['RespectDriverResultSetType'] = False
    info['ShowColumnDescription'] = False
    info['ShowDeleted'] = False
    info['StringDelimiter'] = '"'
    info['SystemDriverSettings'] = ''
    info['TableAlterationServiceName'] = ''
    info['TableRenameServiceName'] = ''
    info['TableTypeFilterMode'] = 3

    info['ThousandDelimiter'] = ''
    info['UseCatalog'] = False
    info['UseCatalogInSelect'] = True
    info['UseSchemaInSelect'] = True
    info['ViewAccessServiceName'] = ''
    info['ViewAlterationServiceName'] = ''
    return info

def getDataSourceLocation(location, dbname, shutdown):
    url = uno.fileUrlToSystemPath('%s/%s' % (location, dbname))
    return '%sfile:%s%s%s' % (g_protocol, url, g_options, g_shutdown if shutdown else '')

def registerDataSource(dbcontext, dbname, url):
    if not dbcontext.hasRegisteredDatabase(dbname):
        dbcontext.registerDatabaseLocation(dbname, url)
    elif dbcontext.getDatabaseLocation(dbname) != url:
        dbcontext.changeDatabaseLocation(dbname, url)

def getKeyMapFromResult(result, keymap=KeyMap(), provider=None):
    for i in range(1, result.MetaData.ColumnCount +1):
        name = result.MetaData.getColumnName(i)
        dbtype = result.MetaData.getColumnTypeName(i)
        value = _getValueFromResult(result, dbtype, i)
        if value is None:
            continue
        if result.wasNull():
            value = None
        if provider:
            value = provider.transform(name, value)
        keymap.insertValue(name, value)
    return keymap

def getSequenceFromResult(result, sequence=None, index=1, provider=None):
    # TODO: getSequenceFromResult(result, sequence=[], index=1, provider=None) is buggy
    # TODO: sequence has the content of last method call!!! sequence must be initialized...
    if sequence is None:
        sequence = []
    i = result.MetaData.ColumnCount
    if 0 < index < i:
        i = index
    if not i:
        return sequence
    name = result.MetaData.getColumnName(i)
    dbtype = result.MetaData.getColumnTypeName(i)
    while result.next():
        value = _getValueFromResult(result, dbtype, i)
        if value is None:
            continue
        if result.wasNull():
            value = None
        if provider:
            value = provider.transform(name, value)
        sequence.append(value)
    return sequence

def _getValueFromResult(result, dbtype, index):
    if dbtype == 'VARCHAR':
        value = result.getString(index)
    elif dbtype == 'TIMESTAMP':
        value = result.getTimestamp(index)
    elif dbtype == 'BOOLEAN':
        value = result.getBoolean(index)
    elif dbtype == 'BIGINT' or dbtype == 'SMALLINT' or dbtype == 'INTEGER':
        value = result.getLong(index)
    else:
        value = None
    return value

def getTablesAndStatements(statement):
    tables = []
    statements = {}
    call = getDataSourceCall(statement.getConnection(), 'getTables')
    for table in getSequenceFromResult(statement.executeQuery(getSqlQuery('getTableName'))):
        statement = False
        columns = []
        primary = []
        unique = []
        constraint = []
        call.setString(1, table)
        result = call.executeQuery()
        while result.next():
            data = getKeyMapFromResult(result, KeyMap())
            statement = data.getValue('View')
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
        format = (table, ','.join(columns))
        query = getSqlQuery('createTable', format)
        print("dbtool._createDynamicTable(): %s" % query)
        tables.append(query)
        if statement:
            names = ['"Value"']
            values = ['?']
            where = []
            for format in constraint:
                names.append('"%s"' % format['Column'])
                values.append('?')
                where.append('"%s"=?' % format['Column'])
            insert = 'INSERT INTO "%s" (%s) VALUES (%s)' % (table, ','.join(names), ','.join(values))
            update = 'UPDATE "%s" SET "Value"=?,"TimeStamp"=? WHERE %s' % (table, ' AND '.join(where))
            print("dbtools.getCreateTableQueries() Insert: %s" % insert)
            print("dbtools.getCreateTableQueries() Update: %s" % update)
            statements['insert%s' % table] = insert
            statements['update%s' % table] = update
    call.close()
    return tables, statements