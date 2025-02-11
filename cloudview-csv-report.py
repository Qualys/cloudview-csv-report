#
# Author: Sean Nicholson
# Purpose: Python3 - Query Qualys API for list of CSA Failures by Cloud Account then post
#          report to Slack channel provided in CSV, Report will list control failures
#          and a list of resources per control
#
#----------------------------------------------------------
#  Script logic flow
#  1 - process a CSV of account info (CSV columns name,accountId,slackChannel,webHook).
#  2 - pull list of CSA evaluations by account
#  3 - iterate list of failed evaluations and retrieve resources for control failures
#  4 - create csv for each account
#----------------------------------------------------------
# Script Input parameters:
# Required:
# --report allAccounts
# --report BU
# --report accountId
#----------------------------------------------------------
# version: 1.0.0
# date: 7.21.2020
#----------------------------------------------------------

import sys, requests, os, time, csv, getopt, logging, yaml, json, base64
#from slackclient import SlackClient
import logging.config
import argparse
import pandas as pd



def setup_logging(default_path='./config/logging.yml',default_level=logging.INFO,env_key='LOG_CFG'):
    """Setup logging configuration"""
    if not os.path.exists("log"):
        os.makedirs("log")
    path = default_path
    value = os.getenv(env_key, None)
    if value:
        path = value
    if os.path.exists(path):
        with open(path, 'rt') as f:
            config = yaml.safe_load(f.read())
        logging.config.dictConfig(config)
    else:
        logging.basicConfig(level=default_level)


def config():
    with open('./config/config.yml', 'r') as config_settings:
        config_info = yaml.safe_load(config_settings)
        accountInfoCSV = str(config_info['defaults']['accountMap']).rstrip()
        URL = str(config_info['defaults']['apiURL']).rstrip()
        if URL == '' or accountInfoCSV == '':
            print("Config information in ./config.yml not configured correctly. Exiting...")
            sys.exit(1)
    return accountInfoCSV, URL


def processAccountList(scope):
    accountInfoCSV, URL = config()
    username = os.environ["QUALYS_API_USERNAME"]
    #password = base64.b64decode(os.environ["QUALYS_API_PASSWORD"])
    password = os.environ["QUALYS_API_PASSWORD"]
    usrPass = str(username)+':'+str(password)
    b64Val = base64.b64encode(usrPass.encode("utf-8"))
    b64Val = b64Val.decode('ASCII')
    headers = {
        'Accept': 'application/json',
        'content-type': 'application/json',
        'X-Requested-With' : 'python requests',
        'Authorization': "Basic %s" % b64Val
    }

    with open(accountInfoCSV,mode='r') as csv_file:
        accountInfo = csv.DictReader(csv_file)
            #print("{0}\n".format(json.dumps(row)))
        if scope == "allAccounts":
            for row in accountInfo:
                controlFailures = cloudviewReport(row['cloud'],row['accountId'], URL, headers)
        else:
            for row in accountInfo:
                if row['accountId'] == scope:
                    controlFailures = cloudviewReport(row['cloud'],row['accountId'], URL, headers)
                    break
                elif row['BU'] == scope:
                    controlFailures = cloudviewReport(row['cloud'],row['accountId'], URL, headers)


def cloudviewReport(cloud, accountID, URL, headers):


    out_file = "reports/" + str(accountID) + "_" "CloudView_Report_" + time.strftime("%Y%m%d-%H%M%S") + ".csv"
    ofile = open(out_file, "w")
    fieldnames = ["Account","Control ID","Control Name","Number of Failed Resources","Failed Resource List","CID Remediation Link"]
    writer = csv.DictWriter(ofile, fieldnames=fieldnames)
    writer.writeheader()
    pageNo = 0
    fullResults = False
    rURL = URL + "/cloudview-api/rest/v1/" + str(cloud) + "/evaluations/" + str(accountID) + "?evaluatedOn:now-8h...now-1s&pageSize=100&pageNo={}".format(str(pageNo))
    rdata = requests.get(rURL, headers=headers)
    logger.info("GET list of control evaluations for Account ID %s - run status code %s", str(accountID), rdata.status_code)
    pagedControlList = []
    controlFailures = []
    controlText = {}
    controlList = json.loads(rdata.text)
    logger.debug("Length of control list content {}".format(len(controlList['content'])))
    while fullResults == False:
        for control in controlList['content']:
            if control['failedResources'] > 0:
                pagedControlList.append(control)
        logger.debug("str(controlList[\'last\']) = {0} and int(controlList[\'totalPages\']) == {1}".format(controlList['last'], str(controlList['totalPages'])))
        if controlList['last'] == True:
            fullResults = True
        else:
            pageNo += 1
            rURL = URL + "/cloudview-api/rest/v1/" + str(cloud) + "/evaluations/" + str(accountID) + "?evaluatedOn:now-8h...now-1s&pageSize=100&pageNo={}".format(str(pageNo))
            rdata = requests.get(rURL, headers=headers)
            logger.info("GET Next Page {0} list of control evaluations for Account ID {1} - run status code {2}".format(str(pageNo), str(accountID), str(rdata.status_code)))
            controlList = json.loads(rdata.text)

    for control in pagedControlList:
        pageNo = 0
        controlText['text'] = ''
        rURL2 = URL + "/cloudview-api/rest/v1/" + str(cloud) + "/evaluations/" + str(accountID) + "/resources/" + str(control['controlId']) + "?evaluatedOn:now-8h...now-1s&pageNo={}&pageSize=50".format(str(pageNo))
        rdata2 = requests.get(rURL2, headers=headers)
        logger.debug("Get Page {0} resource list per account per control request status code {1}".format(str(pageNo), rdata2.status_code))
        logger.debug("Get Page {0} resource list per account per control request resource list \n{1}".format(str(pageNo), rdata2.text))
        failedResources = []
        resourceList = json.loads(rdata2.text)
        logger.info("Resource Details Control ID {0} for {1} Failures".format(str(control['controlId']), str(control['failedResources'])))
        fullResults = False
        while fullResults == False:
            for resource in resourceList['content']:
                logger.debug("Resource Info \n {} \n".format(str(resource)))
                if resource['result'] == "FAIL":
                    failedResources.append(str(resource['resourceId']))
            if resourceList['last'] == True:
                fullResults = True
            else:
                pageNo += 1
                rURL2 = URL + "/cloudview-api/rest/v1/" + str(cloud) + "/evaluations/" + str(accountID) + "/resources/" + str(control['controlId']) + "?evaluatedOn:now-8h...now-1s&pageNo={}&pageSize=50".format(str(pageNo))
                rdata2 = requests.get(rURL2, headers=headers)
                logger.debug("Get Page {0} resource list per account per control request status code {1}".format(str(pageNo), rdata2.status_code))
                logger.debug("Get Page {0} resource list per account per control request resource list \n{1}".format(str(pageNo), rdata2.text))
                resourceList = json.loads(rdata2.text)

        controlText['text'] = "Failed Control CID {0}, Control Name: {1}, Number of Failed Resources {2}\n Failed Resources: \n {3}".format(control['controlId'],control['controlName'], str(control['failedResources']), str(failedResources))

        remediationLink = URL + "/cloudview/controls/cid-" + str(control['controlId']) + ".html"
        writer.writerow({"Account": str(accountID), "Control ID": str(control['controlId']), "Control Name": str(control['controlName']).replace("\n", "") ,"Number of Failed Resources": str(control['failedResources']), "Failed Resource List": str(failedResources).strip("[]"), "CID Remediation Link": str(remediationLink)})
        logger.debug(controlText['text'])

        controlFailures.append(dict(controlText))

    ofile.close()
    df1 = pd.read_csv(out_file)
    df2 = pd.read_csv('cismap.csv')
    left_join = pd.merge (df1,
                          df2,
                          on ='Control ID',
                          how ='left')
    left_join.to_csv( out_file, index=False)

    return controlFailures


setup_logging()
parser = argparse.ArgumentParser()
parser.add_argument("--report", "-r", help="(Required) Run report for specified accounts in scope: python slack_cloudview_alerts.py -r <scope> or python slack_cloudview_alerts.py --report <scope> **** Acceptable <scope> parameters are 'allAccounts', or a BU or accountId listed in cloud-accounts.csv")

args = parser.parse_args()
if not args.report:
    logger.warning("Scope is required to run script, please run python slack_cloudview_alerts.py -h for required command syntax")
    sys.exit(1)

if not os.path.exists("reports"):
    os.makedirs("reports")

if __name__ == "__main__":

    logger = logging.getLogger(__name__)
    logger.info("Running report for scope {}".format(str(args.report)))
    processAccountList(str(args.report))
