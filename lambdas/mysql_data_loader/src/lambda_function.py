from db_data import generate_db_report
from server_data import generate_server_report
import json
from datetime import datetime
from zoneinfo import ZoneInfo
import boto3

def lambda_handler(event, context):

    db_report = {
        "Infrastructure Info" : generate_server_report(),
        "Database Info" : generate_db_report()
    }

    timestamp = datetime.now(ZoneInfo("Asia/Kolkata"))

    s3_client = boto3.client('s3')
    s3_client.put_object(
        Bucket='database-reports-bucket', 
        Key=f"reports/mysql_dba_report_{timestamp}.json",
        Body=json.dumps(db_report, indent=4, default=str),
        ContentType='application/json'
    )
    
    #print(json.dumps(db_report, indent=4, default=str))
    
    return {
        "statusCode": 200,
    }

