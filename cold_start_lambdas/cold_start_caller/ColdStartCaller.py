import json
import boto3
import re
import time
import datetime
import os

lambda_client = boto3.client('lambda')
xray_client = boto3.client('xray')
dynamodb_client = boto3.client('dynamodb')
s3_client = boto3.client('s3')

def lambda_handler(event, context):
    memory_size_list = ["128", "512", "1024", "2048"]
    runtime_list = ['PYTHON38', 'NODEJS12X', 'JAVA11', 'GO1X', 'RUBY27', 'NETCORE31']
    functions = []
    for mem in memory_size_list:
        for runtime in runtime_list:
            functions.append(os.environ[runtime + '_' + mem])
    
    xray_trace_id_dict = invoke_lambda_return_xray_id(functions)

    # wait for 5 mins to allow xray to polulated
    time.sleep(5)
    
    lambda_configs_dict = get_lambda_configs(functions)
    
    timestamp_dict = get_timestamp_from_xray(xray_trace_id_dict)

    report_artifect_dict = merge_timestamp_configs(lambda_configs_dict, timestamp_dict)

    # report data to destinations
    store_data_to_dynamodb(report_artifect_dict)
    store_data_to_s3(report_artifect_dict)


def invoke_lambda_return_xray_id(functions):
    xray_trace_id_dict = {}
    for function in functions:
        response = lambda_client.invoke(
            FunctionName = function,
            InvocationType = 'RequestResponse'
        )
        xray_trace_id = re.match(r'root=(.*);.*', response['ResponseMetadata']['HTTPHeaders']['x-amzn-trace-id']).groups()[0]
        xray_trace_id_dict[function] = xray_trace_id
    return xray_trace_id_dict

def get_lambda_configs(functions):
    lambda_configs_dict = {}
    for function in functions:
        response = lambda_client.get_function_configuration(
            FunctionName=function
        )
        lambda_configs_dict[function] = response
    return lambda_configs_dict

def merge_timestamp_configs(lambda_configs_dict, timestamp_dict):
    report_artifect_dict = {}
    for function in timestamp_dict:
        report_artifect_dict[function] = {
            "Records": timestamp_dict[function],
            "Configs": {
                "FunctionArn": lambda_configs_dict[function]["FunctionArn"],
                "Runtime": lambda_configs_dict[function]["Runtime"],
                "CodeSize": lambda_configs_dict[function]["CodeSize"],
                "MemorySize": lambda_configs_dict[function]["MemorySize"]
            }
        }
    return report_artifect_dict 
        

def get_timestamp_from_xray(xray_trace_id_dict):
    timestamp_dict = {}
    for function in xray_trace_id_dict:
        function_timestamp = {}
        function_timestamp['AWS::X-Ray::Trace-id'] = xray_trace_id_dict[function]

        xray_record = xray_client.batch_get_traces(
            TraceIds=[xray_trace_id_dict[function]]
        )
        lambda_doc = json.loads([seg for seg in xray_record["Traces"][0]['Segments'] if '"AWS::Lambda"' in seg['Document']][0]['Document'])
        function_timestamp['AWS::Lambda::start'] = lambda_doc["start_time"]
        function_timestamp['AWS::Lambda::end'] = lambda_doc["end_time"]

        lambda_function_doc = json.loads([seg for seg in xray_record["Traces"][0]['Segments'] if '"AWS::Lambda::Function"' in seg['Document']][0]['Document'])
        function_timestamp['AWS::Lambda::Function::start'] = lambda_function_doc["start_time"]
        function_timestamp['AWS::Lambda::Function::end'] = lambda_function_doc["end_time"]
        if "subsegments" in lambda_function_doc:
            for subsegment in lambda_function_doc["subsegments"]:
                function_timestamp['AWS::Lambda::Function::' + subsegment['name'] + '::start'] = subsegment['start_time']
                function_timestamp['AWS::Lambda::Function::' + subsegment['name'] + '::end'] = subsegment['end_time']
        timestamp_dict[function] = function_timestamp
    return timestamp_dict       

def store_data_to_dynamodb(report_artifect_dict):
    current_timestamp = datetime.datetime.now()
    expiration_timestamp = current_timestamp + datetime.timedelta(days=60)
    for function in report_artifect_dict:
        item = {
            "PK": 'RECORD|AWS|' + report_artifect_dict[function]["Configs"]["Runtime"]+"|"+str(report_artifect_dict[function]["Configs"]["MemorySize"]),
            "SK": current_timestamp.timestamp(),
            "Type": "RECORD",
            "Records": report_artifect_dict[function]["Records"],
            "Configs": report_artifect_dict[function]["Configs"],
            "TTL": expiration_timestamp.timestamp()
        }
        dynamodb_client.put_item(
            TableName=os.environ['TABLE_NAME'],
            Item=dict_to_item(item)
        )

def store_data_to_s3(report_artifect_dict):
    current_timestamp = datetime.datetime.now()
    key =   "AWS/" + \
            str(current_timestamp.year) + "/"  + \
            str(current_timestamp.month) + "/" + \
            str(current_timestamp.day) + "/" + \
            str(current_timestamp.hour) + "/" + \
            str(current_timestamp.minute) + ".json"
    s3_client.put_object(
        Body=(bytes(json.dumps(report_artifect_dict).encode('UTF-8'))),
        Bucket=os.environ['BACKUP_BUCKET_NAME'],
        Key=key
    )


def dict_to_item(raw):
    if type(raw) is dict:
        resp = {}
        for k,v in raw.items():
            if type(v) is str:
                resp[k] = {
                    'S': v
                }
            elif type(v) is int or type(v) is float:
                resp[k] = {
                    'N': str(v)
                }
            elif type(v) is dict:
                resp[k] = {
                    'M': dict_to_item(v)
                }
            elif type(v) is list:
                resp[k] = []
                for i in v:
                    resp[k].append(dict_to_item(i))
        return resp
    elif type(raw) is str:
        return {
            'S': raw
        }
    elif type(raw) is int or type(raw) is float:
        return {
            'N': str(raw)
        }