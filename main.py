import argparse
import pika
import json
import datetime
from db.utils import check_today_projects, create_new_project, update_project, delete_project

def load_args_schema(action):
    with open('args_schema.json') as f:
        args_schema = json.load(f)
    return args_schema.get(action, [])

def main():
    parser = argparse.ArgumentParser(description='FandanGO application')
    parser.add_argument('--action', choices=['createProject', 'deleteProject', 'copyData'],
                        help='Action to perform', required=True)

    fixed_args, additional_args = parser.parse_known_args()

    # check if the user provided the required args for the chosen action
    args_schema = load_args_schema(fixed_args.action)
    for arg in args_schema:
        parser.add_argument(arg['name'], help=arg['help'], required=arg['required'])
    parser.parse_known_args()

    # format additional args
    additional_args_parsed = {arg.split('=')[0].replace('--', ''): arg.split('=')[1] for arg in additional_args}

    # core internal actions (createProject, deleteProject, etc.)
    if fixed_args.action == 'createProject':
        print('FandanGO will create a new project...')
        today_projects = check_today_projects()
        project_id = datetime.datetime.now().strftime('%Y%m%d') + str(today_projects + 1)
        new_project = (project_id, int(datetime.datetime.now().timestamp()), None, None, None)
        create_new_project(new_project)

    elif fixed_args.action == 'deleteProject':
        print('FandanGO will delete an existing project...')
        delete_project(additional_args_parsed['projectId'])

    # actions involving other plugins
    elif additional_args_parsed['plugin']:
        try:
            # create RabbitMQ connection
            connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
            channel = connection.channel()
            message = {'action': fixed_args.action, 'args': additional_args_parsed}
            # send action to other plugin queue
            channel.basic_publish(exchange='', routing_key=additional_args_parsed['plugin'], body=json.dumps(message))
            print(f'Message sent to {additional_args_parsed["plugin"]} queue')

            # function to process plugins results
            def callback(ch, method, properties, body):
                body = json.loads(body.decode('utf-8'))
                print(f'Message received from the {additional_args_parsed["plugin"]} microservice: {body}')

                # do whatever we have to do depending on the action (copyData, associateProject, etc.)
                if body['success']:
                    if fixed_args.action == 'copyData':
                        update_project(additional_args_parsed['projectId'], 'data_management_system', "'" + additional_args_parsed['plugin'] + "'")
                    elif fixed_args.action == 'associateProject':
                        update_project(additional_args_parsed['projectId'], 'proposal_manager', "'" + additional_args_parsed['plugin'] + "'")

                connection.close()

            # core's queue. This will listen for plugins results
            channel.queue_declare(queue='core')
            # core's queue start listening
            channel.basic_consume(queue='core', on_message_callback=callback, auto_ack=True)
            channel.start_consuming()

        except Exception as e:
            print(f'Error queuing action to microservice to {additional_args_parsed["plugin"]}. Error: {e}')

if __name__ == '__main__':
    main()
