import boto3
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


cloudwatch = boto3.client("cloudwatch", region_name="us-east-1")

INSTANCE_ID = "i-075d1c158084640e8"

def get_metric(namespace, metric_name, dimensions, lookback_minutes=15):
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(minutes=lookback_minutes)

    response = cloudwatch.get_metric_statistics(
        Namespace=namespace,
        MetricName=metric_name,
        Dimensions=dimensions,
        StartTime=start_time,
        EndTime=end_time,
        Period=60,
        Statistics=["Average", "Maximum"]
    )

    datapoints = response.get("Datapoints", [])

    if not datapoints:
        return {
            "current": "N/A",
            "average": "N/A",
            "maximum": "N/A"
        }

    datapoints = sorted(
        datapoints,
        key=lambda x: x["Timestamp"]
    )

    current = round(datapoints[-1]["Average"], 2)
    average = round(
        sum(d["Average"] for d in datapoints) / len(datapoints),
        2
    )
    maximum = round(
        max(d["Maximum"] for d in datapoints),
        2
    )

    return {
        "current": current,
        "average": average,
        "maximum": maximum
    }


infrastructure_performance = {}

def generate_server_report():
    ec2_dimensions = [
        {
            "Name": "InstanceId",
            "Value": INSTANCE_ID
        }
    ]

    cpu = get_metric(
        namespace="AWS/EC2",
        metric_name="CPUUtilization",
        dimensions=ec2_dimensions
    )

    memory = get_metric(
        namespace="CWAgent",
        metric_name="mem_used_percent",
        dimensions=ec2_dimensions
    )

    swap = get_metric(
        namespace="CWAgent",
        metric_name="swap_used_percent",
        dimensions=ec2_dimensions
    )

    disk = get_metric(
        namespace="CWAgent",
        metric_name="disk_used_percent",
        dimensions=ec2_dimensions
    )

    infrastructure_performance["Generated Time"] = f"{datetime.now(ZoneInfo("Asia/Kolkata"))}"
    infrastructure_performance["Instance"] = INSTANCE_ID

    infrastructure_performance["CPU Utilization"] = {
        "Current" : f"{cpu['current']} %",
        "Average" : f"{cpu['average']} %",
        "Maximum" : f"{cpu['maximum']} %"
    }

    infrastructure_performance["Memory Utilization"] = {
        "Current" : f"{memory['current']} %",
        "Average" : f"{memory['average']} %",
        "Maximum" : f"{memory['maximum']} %"
    }

    infrastructure_performance["SWAP Utilization"] = {
        "Current" : f"{swap['current']} %",
        "Average" : f"{swap['average']} %",
        "Maximum" : f"{swap['maximum']} %"
    }

    infrastructure_performance["Disk Utilization"] = {
        "Current" : f"{disk['current']} %",
        "Average" : f"{disk['average']} %",
        "Maximum" : f"{disk['maximum']} %"
    }

    infrastructure_performance["AUTOMATED OBSERVATION"] = {
        "CPU High"     : f"{"YES" if cpu['current'] != "N/A" and cpu['current'] > 80 else "NO"}",

        "Memory High"  : f"{"YES" if memory['current'] != "N/A" and memory['current'] > 85 else "NO"}",

        "Swap High"    : f"{"YES" if swap['current'] != "N/A" and swap['current'] > 20 else "NO"}",

        "Disk High"    : f"{"YES" if disk['current'] != "N/A" and disk['current'] > 80 else "NO"}"
    }

    return infrastructure_performance

    
