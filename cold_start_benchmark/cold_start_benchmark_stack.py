from aws_cdk import (
    core,
    aws_lambda as lambda_,
    aws_iam as iam_,
    aws_dynamodb as dynamodb_,
    aws_s3 as s3_,
    aws_events as events_,
    aws_events_targets as targets_,
    aws_cloudwatch as cloudwatch_,
    aws_cloudwatch_actions as cloudwatch_actions_,
    aws_sns as sns_,
    aws_sns_subscriptions as sns_subs_
)
import json

class ColdStartBenchmarkStack(core.Stack):

    def __init__(self, scope: core.Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # load configs from "./comfigurations/config.json"
        configs = {}
        with open("./configurations/config.json") as json_file:
            configs = json.load(json_file)

        # Default lambdas for testing
        mem_list = configs['MemorySizeList']
        cold_start_lambdas = {}
        for mem in mem_list:
            python38_lambda = lambda_.Function(self, id="coldstart_python38_" + str(mem) + "_", 
                runtime=lambda_.Runtime.PYTHON_3_8, handler="lambda_function.lambda_handler", memory_size=mem,
                tracing=lambda_.Tracing.ACTIVE, code=lambda_.Code.asset("./cold_start_lambdas/python38"))
            cold_start_lambdas['PYTHON38_' + str(mem)] = python38_lambda
            
        for mem in mem_list:
            nodejs12x_lambda = lambda_.Function(self, id="coldstart_nodejs12x" + str(mem) + "_",
                runtime=lambda_.Runtime.NODEJS_12_X, handler="index.handler", memory_size=mem,
                tracing=lambda_.Tracing.ACTIVE, code=lambda_.Code.asset("./cold_start_lambdas/nodejs12x"))
            cold_start_lambdas['NODEJS12X_' + str(mem)] = nodejs12x_lambda

        for mem in mem_list:
            go1x_lambda = lambda_.Function(self, id="coldstart_go1x" + str(mem) + "_",
                runtime=lambda_.Runtime.GO_1_X, handler="hello", memory_size=mem,
                tracing=lambda_.Tracing.ACTIVE, code=lambda_.Code.asset("./cold_start_lambdas/go1x"))
            cold_start_lambdas['GO1X_' + str(mem)] = go1x_lambda

        for mem in mem_list:
            netcore31_lambda = lambda_.Function(self, id="coldstart_netcore31" + str(mem) + "_",
                runtime=lambda_.Runtime.DOTNET_CORE_3_1, handler="LambdaTest::LambdaTest.LambdaHandler::handleRequest",
                tracing=lambda_.Tracing.ACTIVE, code=lambda_.Code.asset("./cold_start_lambdas/netcore31"), memory_size=mem,)
            cold_start_lambdas['NETCORE31_' + str(mem)] = netcore31_lambda

        for mem in mem_list:
            java11corretto_lambda = lambda_.Function(self, id="coldstart_java11corretto" + str(mem) + "_",
                runtime=lambda_.Runtime.JAVA_11, handler="example.Hello::handleRequest", memory_size=mem,
                tracing=lambda_.Tracing.ACTIVE, code=lambda_.Code.asset("./cold_start_lambdas/java11corretto"))
            cold_start_lambdas['JAVA11_' + str(mem)] = java11corretto_lambda

        for mem in mem_list:
            ruby27_lambda = lambda_.Function(self, id="coldstart_ruby27" + str(mem) + "_",
                runtime=lambda_.Runtime.RUBY_2_7, handler="lambda_function.lambda_handler", memory_size=mem,
                tracing=lambda_.Tracing.ACTIVE, code=lambda_.Code.asset("./cold_start_lambdas/ruby27"))
            cold_start_lambdas['RUBY27_' + str(mem)] = ruby27_lambda

        # Caller
        cold_start_caller = lambda_.Function(self, id="cold_start_caller", 
            runtime=lambda_.Runtime.PYTHON_3_8, handler="ColdStartCaller.lambda_handler",
            code=lambda_.Code.asset("./cold_start_lambdas/cold_start_caller"),
            timeout=core.Duration.seconds(180))
        cold_start_caller.role.add_managed_policy(iam_.ManagedPolicy.from_aws_managed_policy_name("AWSXrayReadOnlyAccess"))
        cold_start_caller.role.add_to_policy(iam_.PolicyStatement(
            effect=iam_.Effect.ALLOW, 
            actions=['lambda:GetFunctionConfiguration'],
            resources=["*"]))
        for lambda_name in cold_start_lambdas:
            cold_start_caller.add_environment(lambda_name, cold_start_lambdas[lambda_name].function_arn)
            cold_start_lambdas[lambda_name].grant_invoke(cold_start_caller)

        # DynamoDB
        cold_start_table = dynamodb_.Table(self, 
            id="cold_start_benchmark_table", 
            partition_key=dynamodb_.Attribute(name="PK", type=dynamodb_.AttributeType.STRING),
            sort_key=dynamodb_.Attribute(name="SK", type=dynamodb_.AttributeType.NUMBER),
            time_to_live_attribute="TTL")
        cold_start_table.grant_write_data(cold_start_caller)
        cold_start_caller.add_environment('TABLE_NAME', cold_start_table.table_name)

        # S3
        life_cycle_rule = s3_.LifecycleRule(transitions=[
            s3_.Transition(storage_class=s3_.StorageClass.INFREQUENT_ACCESS, transition_after=core.Duration.days(30))])
        cold_start_backup_s3 = s3_.Bucket(self, "cold_start_benchmark_backup", lifecycle_rules=[life_cycle_rule])
        cold_start_backup_s3.grant_write(cold_start_caller)
        cold_start_caller.add_environment('BACKUP_BUCKET_NAME', cold_start_backup_s3.bucket_name)

        # CW event
        cron_job = events_.Rule(self, "cold_start_caller_cron_job", 
            description="Run cold start caller twice every 1 hour",
            schedule=events_.Schedule.cron(minute="0,1"),
            targets=[targets_.LambdaFunction(cold_start_caller)]
        )

        # alarm when caller failed, send email for notification
        errorAlarm = cloudwatch_.Alarm(self, "cold_start_caller_error_alarm",
            metric=cloudwatch_.Metric(
                metric_name="Errors",
                namespace="AWS/Lambda",
                period=core.Duration.minutes(5),
                statistic="Maximum",
                dimensions={"FunctionName": cold_start_caller.function_name}
            ),
            evaluation_periods=1,
            datapoints_to_alarm=1,
            threshold=1,
            actions_enabled=True,
            alarm_description="Alarm when cold start caller failed",
            alarm_name="cold_start_caller_errer_alarm",
            comparison_operator=cloudwatch_.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch_.TreatMissingData.MISSING
        )
        cold_start_caller_error_alarm_topic = sns_.Topic(self, "cold_start_caller_error_alarm_topic", 
                    display_name="ColdStartCallerErrorAlarmTopic",
                    topic_name="ColdStartCallerErrorAlarmTopic")
        cold_start_caller_error_alarm_topic.add_subscription(sns_subs_.EmailSubscription(configs['AlarmNotificationEmailAddress']))
        errorAlarm.add_alarm_action(
            cloudwatch_actions_.SnsAction(cold_start_caller_error_alarm_topic))

        
        # Summarizer
        cold_start_summarizer = lambda_.Function(self, id="cold_start_summarizer",
            runtime=lambda_.Runtime.PYTHON_3_8, handler="ColdStartSummarizer.lambda_handler",
            code=lambda_.Code.asset("./cold_start_lambdas/cold_start_summarizer"),
            timeout=core.Duration.seconds(10)
        )
        cold_start_table.grant_read_write_data(cold_start_summarizer)
        cold_start_summarizer.add_environment('TABLE_NAME', cold_start_table.table_name)
        
        # setup CW event for summarizer
        cron_job_summarizer = events_.Rule(self, "cold_start_summarizer_cron_job", 
            description="Run cold start summarizer once every day",
            schedule=events_.Schedule.cron(minute='30', hour='0'),
            targets=[targets_.LambdaFunction(cold_start_summarizer)]
        )

        # error alarm for summarizer
        errorAlarm_summarizer = cloudwatch_.Alarm(self, "cold_start_summarizer_error_alarm",
            metric=cloudwatch_.Metric(
                metric_name='Errors',
                namespace='AWS/Lambda',
                period=core.Duration.minutes(5),
                statistic='Maximum',
                dimensions={'FunctionName': cold_start_summarizer.function_name}
            ),
            evaluation_periods=1,
            datapoints_to_alarm=1,
            threshold=1,
            actions_enabled=True,
            alarm_description="Alarm when cold start summarizer failed",
            alarm_name="cold_start_summarizer_errer_alarm",
            comparison_operator=cloudwatch_.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch_.TreatMissingData.MISSING
        )
        cold_start_summarizer_error_alarm_topic = sns_.Topic(self, "cold_start_summarizer_error_alarm_topic", 
                    display_name="ColdStartSummarizerErrorAlarmTopic",
                    topic_name="ColdStartSummarizerErrorAlarmTopic")
        cold_start_summarizer_error_alarm_topic.add_subscription(sns_subs_.EmailSubscription(configs['AlarmNotificationEmailAddress']))
        errorAlarm_summarizer.add_alarm_action(
            cloudwatch_actions_.SnsAction(cold_start_summarizer_error_alarm_topic))