import logging
import boto3
import datetime
import pytz
import os

logging.getLogger('botocore').setLevel(logging.CRITICAL)
logging.getLogger('urllib3').setLevel(logging.CRITICAL)


def _get_tasks_in_cluster(ecs_client, cluster_name, next_token=None):
    """Get the running tasks in the given cluster"""
    result = []
    if next_token:
        query_result = ecs_client.list_tasks(cluster=cluster_name, nextToken=next_token)
    else:
        query_result = ecs_client.list_tasks(cluster=cluster_name)

    if 'ResponseMetadata' in query_result:
        if 'HTTPStatusCode' in query_result['ResponseMetadata']:
            if query_result['ResponseMetadata']['HTTPStatusCode'] == 200:
                if 'nextToken' in query_result:
                    result.extend(query_result['taskArns'])
                    result.extend(_get_tasks_in_cluster(ecs_client=ecs_client,
                                                       cluster_name=cluster_name,
                                                       next_token=query_result['nextToken']))
                else:
                    result.extend(query_result['taskArns'])
    return result


def cleanup_tasks(task_prefix, max_age, cluster_name=None, exclude_filters=None, region=None, dry_run=False):
    """
    Clean up any long-running tasks that are older than max_age
    :param task_prefix: prefix for the task name to clean up
    :param max_age: Maximum age of the task, if > than this, kill it
    :param cluster_name: Cluster to query, if none provided, use cluster *this* instance is in
    :param exclude_filters: exclude any tasks that match filters
    :param region: AWS Region to query, if none provided, use region for *this* instance
    :param dry_run: dry run only - no changes
    """
    if exclude_filters is None:
        exclude_filters = []
    logging.info(f'Looking for tasks with the prefix {task_prefix} in the {cluster_name} cluster')
    logging.info(f'Any tasks older than {max_age} hours will be terminated')
    session = boto3.session.Session(region_name=region)
    ecs_client = session.client('ecs')
    running_tasks = _get_tasks_in_cluster(ecs_client, cluster_name, next_token=None)
    logging.info(f'Found {len(running_tasks)} running tasks in cluster: {cluster_name}')
    # When describing tasks, can only query 100 at a time - break running_tasks into groups of 100
    task_list_groups_list = [running_tasks[i:i + 100] for i in range(0, len(running_tasks), 100)]
    for group in task_list_groups_list:
        query_result = ecs_client.describe_tasks(cluster=cluster_name, tasks=group)
        tasks = query_result['tasks']
        for task in tasks:
            task_arn = task['taskArn']
            logging.debug('   Processing task ARN: %s ' % task_arn)
            task_family = task['group']
            if any(filter in task_family for filter in exclude_filters):
                logging.debug(f"      Excluding: the task family ({task_family}) is in the exclude list")
                continue
            if task_prefix not in task_family:
                logging.debug(f"      Skipping: the task family ({task_family}) doesn't match the given prefix")
                continue
            if 'startedAt' in task:
                start_time = task['startedAt']
                start_time_utc = start_time.astimezone(pytz.utc)
                time_now_utc = datetime.datetime.now(pytz.UTC)
                logging.debug(f'      Started at      : {str(start_time)}')
                logging.debug(f'      Started at (UTC): {str(start_time_utc)}')
                logging.debug(f'      Time now   (UTC): {str(time_now_utc)}')
                running_time = time_now_utc - start_time_utc
                running_time_seconds = running_time.total_seconds()
                running_time_minutes = int(running_time_seconds // 60)
                running_time_hours = int(running_time_seconds // 3600)
                logging.debug(f'      Running for : ~{running_time_minutes} minutes')
                if running_time_hours > max_age:
                    logging.info(f'         *** Terminating task ({task_arn}) due to old age (> {max_age} hours)')
                    reason = 'Killing task due to old age'
                    if not dry_run:
                        ecs_client.stop_task(cluster=cluster_name, task=task_arn, reason=reason)
                    else:
                        logging.warning('         *** dry run selected, Task will not be killed')
            else:
                # No startedAt time - this must be just starting up - ignore it
                logging.warning('      * no startedAt time - ignoring for now')


def lambda_handler(event, context):
    log_level = os.environ.get('LOG_LEVEL', 'INFO')
    if 'debug' in log_level.lower():
        logging_level = logging.DEBUG
    else:
        logging_level = logging.INFO
    logging.getLogger().setLevel(logging_level)

    logging.debug(f'Event: {event}')
    cluster_name = event.get('cluster_name', None)
    task_name_prefix = event.get('task_name_prefix', None)
    exclude_filters = event.get('exclude_filters', [])
    max_age = event.get('max_age', 48)
    region = event.get('region', None)
    dry_run = event.get('dry_run', False)

    cleanup_tasks(task_prefix=task_name_prefix,
                  max_age=max_age,
                  cluster_name=cluster_name,
                  exclude_filters=exclude_filters,
                  region=region,
                  dry_run=dry_run)
