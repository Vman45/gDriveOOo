#!
# -*- coding: utf_8 -*-

import uno
import unohelper

from com.sun.star.lang import XServiceInfo
from com.sun.star.ucb import XContentIdentifierFactory
from com.sun.star.ucb import XContentProvider
from com.sun.star.ucb import XContentProviderFactory
from com.sun.star.ucb import XContentProviderSupplier
from com.sun.star.ucb import XParameterizedContentProvider
from com.sun.star.logging.LogLevel import INFO
from com.sun.star.logging.LogLevel import SEVERE

from gdrive import g_plugin
from gdrive import g_provider
from gdrive import getLogger
from gdrive import getUcp

g_proxy = 'com.sun.star.ucb.ContentProviderProxy'

# pythonloader looks for a static g_ImplementationHelper variable
g_ImplementationHelper = unohelper.ImplementationHelper()
g_ImplementationName = '%s.ContentProviderProxy' % g_plugin


class ContentProviderProxy(unohelper.Base,
                           XServiceInfo,
                           XContentIdentifierFactory,
                           XContentProvider,
                           XContentProviderFactory,
                           XContentProviderSupplier,
                           XParameterizedContentProvider):
    def __init__(self, ctx):
        msg = "ContentProviderProxy for plugin: %s loading ..." % g_plugin
        self.ctx = ctx
        self.scheme = ''
        self.plugin = ''
        self.replace = True
        self.Logger = getLogger(self.ctx)
        msg += " Done"
        self.Logger.logp(INFO, 'ContentProviderProxy', '__init__()', msg)

    # XContentProviderFactory
    def createContentProvider(self, service):
        provider = None
        level = INFO
        msg = "Service: %s loading ..." % service
        ucp = self.ctx.ServiceManager.createInstanceWithContext(g_provider, self.ctx)
        if not ucp:
            level = SEVERE
            msg += " ERROR: requested service is not available..."
        else:
            msg += " Done"
            provider = ucp.registerInstance(self.scheme, self.plugin, self.replace)
        self.Logger.logp(level, 'ContentProviderProxy', 'createContentProvider()', msg)
        return provider

    # XContentProviderSupplier
    def getContentProvider(self):
        provider = None
        level = INFO
        msg = "Need to get UCP: %s ..." % g_provider
        ucp = getUcp(self.ctx, self.scheme)
        if ucp.supportsService(g_proxy):
            provider = self.createContentProvider(g_provider)
            if not provider:
                level = SEVERE
                msg += " ERROR: requested service is not available..."
            else:
               msg += " Done"
        else:
            msg += " Done"
            provider = ucp
        self.Logger.logp(level, 'ContentProviderProxy', 'getContentProvider()', msg)
        return provider

    # XParameterizedContentProvider
    def registerInstance(self, scheme, plugin, replace):
        msg = "Register Scheme/Plugin/Replace: %s/%s/%s ..." % (scheme, plugin, replace)
        self.scheme = scheme
        self.plugin = plugin
        self.replace = replace
        msg += " Done"
        self.Logger.logp(INFO, 'ContentProviderProxy', 'registerInstance()', msg)
        return self
    def deregisterInstance(self, scheme, plugin):
        self.getContentProvider().deregisterInstance(scheme, plugin)
        msg = "ContentProviderProxy.deregisterInstance(): %s - %s ... Done" % (scheme, plugin)
        self.Logger.logp(INFO, 'ContentProviderProxy', 'deregisterInstance()', msg)

    # XContentIdentifierFactory
    def createContentIdentifier(self, identifier):
        return self.getContentProvider().createContentIdentifier(identifier)

    # XContentProvider
    def queryContent(self, identifier):
        return self.getContentProvider().queryContent(identifier)
    def compareContentIds(self, identifier1, identifier2):
        return self.getContentProvider().compareContentIds(identifier1, identifier2)

    # XServiceInfo
    def supportsService(self, service):
        return g_ImplementationHelper.supportsService(g_ImplementationName, service)
    def getImplementationName(self):
        return g_ImplementationName
    def getSupportedServiceNames(self):
        return g_ImplementationHelper.getSupportedServiceNames(g_ImplementationName)


g_ImplementationHelper.addImplementation(ContentProviderProxy,
                                         g_ImplementationName,
                                        (g_ImplementationName, g_proxy))
