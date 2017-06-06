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


# Prerequisites
* Docker must be installed
* Either an AWS role (if running on EC2) or an access key/secret key

# Usage

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
