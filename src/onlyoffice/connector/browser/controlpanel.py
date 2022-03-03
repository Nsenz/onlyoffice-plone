#
# (c) Copyright Ascensio System SIA 2022
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

from plone.app.registry.browser.controlpanel import ControlPanelFormWrapper
from plone.app.registry.browser.controlpanel import RegistryEditForm
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from z3c.form.interfaces import WidgetActionExecutionError
from zope import schema
from zope.interface import Interface
from zope.interface import Invalid
from zope.interface import invariant
from plone import api
from zope.component import getUtility
from plone.registry.interfaces import IRegistry
from DateTime import DateTime
from onlyoffice.connector.core import conversionUtils
from urllib.request import urlopen
from onlyoffice.connector.interfaces import _
from onlyoffice.connector.interfaces import logger
from onlyoffice.connector.core import utils
from onlyoffice.connector.core.config import Config

import json
import requests

class IOnlyofficeControlPanel(Interface):

    docUrl = schema.TextLine(
        title=_(u'Document Editing service'),
        required=True,
        default=u'https://documentserver/',
    )

    docUrlPublicValidation = schema.Bool(
        required=True,
        default=True
    )

    demoEnabled = schema.Bool(
        title=_(u"Connect to demo ONLYOFFICE Document Server"),
        description=_(u"This is a public test server, please do not use it for private sensitive data. The server will be available during a 30-day period."),
        required=False,
        default=False
    )

    jwtSecret = schema.TextLine(
        title=_(u'Secret key (leave blank to disable)'),
        required=False,
    )
    
    ploneUrl = schema.TextLine(
        title=_(u'Server address for internal requests from the Document Editing Service'),
        required=False
    )

    docInnerUrl = schema.TextLine(
        title=_(u'Document Editing Service address for internal requests from the server'),
        required=False
    )

    @invariant
    def settings_validation_demo(data):
        if data.demoEnabled and utils.getDemoAvailable(True):
            demoUrl = Config(getUtility(IRegistry)).demoDocUrl
            demoSecret = Config(getUtility(IRegistry)).demoJwtSecret
            ploneInnerUrl = data.ploneUrl

            check_doc_serv_url(demoUrl, "demoEnabled", True)

            check_doc_serv_command_service(demoUrl, demoSecret, True)

            check_doc_serv_convert_service(demoUrl, ploneInnerUrl, demoSecret, True)

            utils.setDemo()

    @invariant
    def settings_validation(data):
        if not data.demoEnabled or not utils.getDemoAvailable(True): 
            if (not data.docUrlPublicValidation):
                raise WidgetActionExecutionError(
                    "docUrl",
                    Invalid(_(u'ONLYOFFICE cannot be reached'))
                )

            portalUrl = api.portal.get().absolute_url()
            ploneInnerUrl = data.ploneUrl

            if (portalUrl.startswith("https") and not data.docUrl.startswith("https")):
                raise WidgetActionExecutionError(
                    "docUrl",
                    Invalid(_(u'Mixed Active Content is not allowed. HTTPS address for Document Server is required.'))
                )

            if data.docInnerUrl != None and data.docInnerUrl != "":
                nameField = "docInnerUrl"
                url = data.docInnerUrl
            else :
                nameField = "docUrl"
                url = data.docUrl

            url = url if url.endswith("/") else url + "/"

            check_doc_serv_url(url, nameField, False)

            check_doc_serv_command_service(url, data.jwtSecret, False)

            check_doc_serv_convert_service(url, ploneInnerUrl, data.jwtSecret, False)

def check_doc_serv_url(url, nameField, demo):
    logger.debug("Checking docserv url")
    try:
        response = urlopen(url + "healthcheck")
        healthcheck = response.read()
        if not healthcheck:
            raise Exception(url + "healthcheck returned false.")
    except Exception as e: 
        raise WidgetActionExecutionError(
                nameField,
                Invalid(get_message_error(_(u'ONLYOFFICE cannot be reached'), demo))
            )

def check_doc_serv_command_service(url, jwtSecret, demo):
    logger.debug("Checking docserv commandservice")
    try:
        headers = { "Content-Type" : "application/json" }
        bodyJson = { "c" : "version" }

        if jwtSecret != None and jwtSecret != "":
            payload = { "payload" :  bodyJson }

            headerToken = utils.createSecurityToken(payload, jwtSecret)
            header = Config(getUtility(IRegistry)).demoHeader if demo else utils.getJwtHeaderEnv()
            headers[header] = "Bearer " + headerToken

            token = utils.createSecurityToken(bodyJson, jwtSecret)
            bodyJson["token"] = token

        response = requests.post(url + "coauthoring/CommandService.ashx", data = json.dumps(bodyJson), headers = headers)

        if response.json()["error"] == 6:
            nameField = "demoEnabled" if demo else "jwtSecret"

            raise WidgetActionExecutionError(
                nameField,
                Invalid(get_message_error(_(u"Authorization error"), demo))
            )

        if response.json()["error"] != 0:
            raise Exception(url + "coauthoring/CommandService.ashx returned error: " + str(response.json()["error"]))
    except WidgetActionExecutionError:
        raise
    except Exception as e:
        logger.error(e)
        if demo:
            raise WidgetActionExecutionError(
                "demoEnabled",
                Invalid(get_message_error(_(u"Error when trying to check CommandService"), demo))
            )
        else:
            raise Invalid(_(u"Error when trying to check CommandService"))

def check_doc_serv_convert_service(docUrl, ploneInnerUrl, jwtSecret, demo):
    logger.debug("Checking docserv convertservice")

    key = int(DateTime())
    url = utils.getTestConvertDocUrl(ploneInnerUrl)
    header = Config(getUtility(IRegistry)).demoHeader if demo else utils.getJwtHeaderEnv()
    jwtEnabled = bool(jwtSecret)

    data, error = conversionUtils.convert(key, url, "txt", "txt", None, False, docUrl, jwtEnabled, jwtSecret, header)

    if error: 
        if demo:
            raise WidgetActionExecutionError(
                "demoEnabled",
                Invalid(get_message_error(_(u"Error when trying to check ConvertService"), demo))
            )
        else:
            raise Invalid(_(u"Error when trying to check ConvertService"))

def get_message_error(message, demo):
    if demo:
        return _(u'Error connecting to demo server (${error})', mapping = {
            "error": message
        })
    else:
        return message

class OnlyofficeControlPanelForm(RegistryEditForm):
    schema = IOnlyofficeControlPanel
    id = "OnlyofficeControlPanelForm"
    schema_prefix = "onlyoffice.connector"
    label = _(u'ONLYOFFICE Configuration')

class OnlyofficeControlPanelView(ControlPanelFormWrapper):
    form = OnlyofficeControlPanelForm
    index = ViewPageTemplateFile("templates/controlpanel.pt")

    def settings(self):
        output = []

        if utils.getDemoAvailable(True):
            output.append("demo_available")

        return " ".join(output)