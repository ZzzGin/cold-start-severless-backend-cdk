import boto3
import datetime
import os

dynamodb_client = boto3.client('dynamodb')

def lambda_handler(event, context):
    memory_size_list = ["128", "512", "1024", "2048"]
    runtime_list = ['python3.8', 'nodejs12.x', 'java11', 'go1.x', 'ruby2.7', 'dotnetcore3.1']
    provider_list = ['AWS']

    # partition key
    dynamodb_pk = []
    for provider in provider_list:
        for mem in memory_size_list:
            for runtime in runtime_list:
                dynamodb_pk.append('RECORD|' + provider + '|' + runtime + '|' + mem)
    
    # sort key
    current_timestamp = datetime.datetime.now()
    one_day_ago_timestamp = current_timestamp - datetime.timedelta(days=1)

    summaries = {}
    cold_timestamp_label = [
        'AWS::Lambda::start',
        'AWS::Lambda::Function::Initialization::start',
        'AWS::Lambda::Function::Initialization::end',
        'AWS::Lambda::Function::start',
        'AWS::Lambda::Function::Invocation::start',
        'AWS::Lambda::Function::Invocation::end',
        'AWS::Lambda::Function::Overhead::start',
        'AWS::Lambda::Function::Overhead::end',
        'AWS::Lambda::Function::end',
        'AWS::Lambda::end'
    ]
    warm_timestamp_label = [
        'AWS::Lambda::start',
        'AWS::Lambda::Function::start',
        'AWS::Lambda::Function::Invocation::start',
        'AWS::Lambda::Function::Invocation::end',
        'AWS::Lambda::Function::Overhead::start',
        'AWS::Lambda::Function::Overhead::end',
        'AWS::Lambda::Function::end',
        'AWS::Lambda::end'
    ]
    for pk in dynamodb_pk:
        result = dynamodb_client.query(
            TableName=os.environ['TABLE_NAME'],
            KeyConditionExpression="#pk = :pk and #sk BETWEEN :start and :end",
            ExpressionAttributeNames={
                "#pk": "PK",
                "#sk": "SK"
            },
            ExpressionAttributeValues={
                ":pk": { "S" : pk },
                ":start": { "N" : str(one_day_ago_timestamp.timestamp()) },
                ":end": { "N" : str(current_timestamp.timestamp()) }
            }
        )
        if result['Count'] == 0:
            continue
        cold_item_data_sum = {}
        warm_item_data_sum = {}
        cold_item_count = 0
        warm_item_count = 0
        for item in result['Items']:
            start_timestamp = timestamp_extract(item, 'AWS::Lambda::start')
            if 'AWS::Lambda::Function::Initialization::start' in item['Records']['M']:
                cold_item_count += 1
                for label in cold_timestamp_label:
                    cold_item_data_sum[label] = cold_item_data_sum.get(label, datetime.timedelta(0)) + (timestamp_extract(item, label) - start_timestamp)
            else:
                warm_item_count += 1
                for label in warm_timestamp_label:
                    warm_item_data_sum[label] = warm_item_data_sum.get(label, datetime.timedelta(0)) + (timestamp_extract(item, label) - start_timestamp)
        for label in cold_item_data_sum:
            cold_item_data_sum[label] /= cold_item_count
        for label in warm_item_data_sum:
            warm_item_data_sum[label] /= warm_item_count
        summaries['Cold'] = cold_item_data_sum
        summaries['Warm'] = warm_item_data_sum
        store_data_to_dynamodb(
            summaries,
            result['Items'][0]['Configs']['M']['Runtime']['S'],
            str(result['Items'][0]['Configs']['M']['MemorySize']['N'])
        )
        

def store_data_to_dynamodb(summary, runtime, memory_size):
    current_timestamp = datetime.datetime.now()
    expiration_timestamp = current_timestamp + datetime.timedelta(days=3*365)
    item = {
        "PK": 'SUMMARY|AWS|' + runtime + '|' + memory_size,
        "SK": current_timestamp.timestamp(),
        "Type": "SUMMARY",
        "Summary": summary,
        "TTL": expiration_timestamp.timestamp()
    }
    dynamodb_client.put_item(
        TableName=os.environ['TABLE_NAME'],
        Item=dict_to_item(item)
    )



def timestamp_extract(item, key):
    try:
        return datetime.datetime.fromtimestamp(float(item['Records']['M'][key]['N']))
    except:
        return datetime.datetime.fromtimestamp(float(item['Records']['M']["AWS::Lambda::start"]['N']))

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
            elif type(v) is datetime.timedelta:
                resp[k] = {
                    'N': str(v.total_seconds())
                }
        return resp
    elif type(raw) is str:
        return {
            'S': raw
        }
    elif type(raw) is int or type(raw) is float:
        return {
            'N': str(raw)
        }
    

if __name__ == "__main__":
    lambda_handler(None, None)