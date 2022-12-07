# task-cleanup
Monitors an ECS cluster for running tasks of a particular family and cycles the tasks if the age is greater than 
a given threshold

# Purpose
It's possible for tasks running in ECS that are 'one-time' tasks, that *should* have a set lifetime to hang,
and never get killed, thereby taking up resources on the cluster than could be used by other tasks. These tasks
should be stopped and removed if they are older than expected.

Since manual work sucks, we've developed this solution which will kill any tasks (of the given family) if
the age of the task is greater than the given max-age (defaults to 48 hours).

Auto-remediation FTW!

# Solutions
Two separate solutions are provided here. You can run this in a docker container (and hence schedule it as an ECS
task) or you can run it as a lambda (and schedule the lambda run)

## Lambda based

### Usage
This tool was developed with the idea of it being run periodically. This can be accomplished using a lambda that
is scheduled to be invoked on a periodic basis.

Included here is a sample samconfig.toml file that can be filled in with appropriate values. If you would like to 
operate on more than one cluster (eg. multiple regions) then you can modify the template.yaml and add more events
similar to the exiting `ScheduleUsEast1` event

Once all values have been filled in, you can build and deploy the lambda as follows:

```bash
cd lambda
sam build && sam deploy --config-env prod --profile <aws_cli_profile_name>
```

## Docker based

### Prerequisites
* Docker must be installed
* Either an AWS role (if running on EC2) or an access key/secret key

### Usage

The easiest way to run the tool is from docker (because docker rocks).
You will need to  pass in variables specific to the ECS task you want to affect

```bash
docker pull signiant/task-cleanup
```

```bash
docker run \
   signiant/task-cleanup \
       --task-name-prefix one-time-task \
       --cluster-name test-cluster \
       --max-age 30
       --region us-east-1 \
       --dryrun
```

In this example, the arguments after the image name are

* --task name prefix <prefix for the one time tasks to monitor>
* --cluster-name <ECS cluster name>
* --max-age <max age of task in hours>
* --region <AWS region>
* --dryrun (don't actually kill any tasks - display only)

In the above example, we query the cluster for tasks using task definitions beginning with one-time-task (done this 
way because cloudformation generated task definitions have a random suffix appended).  Once we have found the active
task definitons, we check the given cluster for running tasks using those task defintions that are older than the 
given max-age (30 hours in this case), and then stop those tasks.

To use an AWS access key/secret key rather than a role:

```bash
docker run \
  -e AWS_ACCESS_KEY_ID=XXXXXX \
  -e AWS_SECRET_ACCESS_KEY=XXXXX \
  signiant/task-cleanup \
        --task-name-prefix one-time-task \
        --cluster-name test-cluster \
        --region us-east-1 \
```
