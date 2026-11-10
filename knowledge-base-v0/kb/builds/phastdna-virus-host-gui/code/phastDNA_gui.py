import flask
import subprocess
import mmap
import json
import re
from pathlib import Path
from collections import defaultdict


app = flask.Flask(__name__, template_folder=".")

current_task_file = ''
ptrs = defaultdict(dict)

# tasks = {}
hypers_lookup = {
    '--dim': 'Word vector size',
    '--minn': 'Minimum k-mer size',
    '--maxn': 'Maximum k-mer size',
    '--fraglen': 'Read length',
    '--samples': 'Read samples number',
    '--lrate': 'Learning rate',
    '--ulr': 'Learning rate update rate',
    '--epochs': 'Epochs number',
    '--noise': 'Noise (mutations)',
    '--considered': 'Considered hosts',
    '--loss': 'Loss function'
}


@app.route('/')
def index():
    return flask.render_template('index.html')


@app.route("/task", methods=['GET', 'POST'])
def test_f():
    if flask.request.method == 'POST':
        data = flask.request.form
        multi = flask.request.form.getlist('--loss')

        # prepare log file - otherwise communication between site and phastdna fails
        output_dir = Path(data["--output"])
        output_dir.mkdir(parents=True, exist_ok=True)
        task_name = f'{output_dir.name}'
        task_file_obj = open(f'{data["--output"]}/PHastDNA.log', 'a')
        task_file_obj.write(" ")
        task_file_obj.close()

        global current_task_file
        global ptr
        current_task_file = task_name
        ptr = 0

        ptrs[task_name]['ptr'] = 0
        ptrs[task_name]['path'] = f'{data["--output"]}/PHastDNA.log'

        if "--hosts" in data:
            arguments = []
            mutable_data = dict(data)
            print(mutable_data)
            filtered_dict = {('-'.join(k.split('-')[:-1]) if k.endswith('-lower') or k.endswith('-upper') else k): ((mutable_data[f'{"-".join(k.split("-")[:-1])}-lower'], mutable_data[f'{"-".join(k.split("-")[:-1])}-upper']) if k.endswith('-lower') or k.endswith('-upper') else v) for k, v in mutable_data.items()}
            if len(multi) > 1:
                filtered_dict.update({'--loss': tuple(multi)})
            filtered_dict.pop('search_terms')

            print(filtered_dict)
            search_space = {}
            for key, value in filtered_dict.items():
                arguments.append(key)
                if isinstance(value, tuple):
                    arguments.extend(value)
                    search_space[key] = value
                else:
                    arguments.append(value)
            print(*arguments)
            print(['python', 'phastdna.py', *arguments])
            command = ['python', 'phastdna.py', *arguments]
            cmd = subprocess.Popen(command)
            return flask.render_template('task.html',
                                        mode="train",
                                        task_name=task_name,
                                        iters=filtered_dict['--iter'],
                                        full_cmd=" ".join(command),
                                        search_space=search_space,
                                        hypers_lookup=hypers_lookup)
        if "--classifier" in data:
            mutable_data = dict(data)
            pred_file = output_dir.joinpath("predictions.csv")
            arguments = [elem for sub_tuple in mutable_data.items() for elem in sub_tuple]
            command = ['python', 'phastdna.py', *arguments]
            cmd = subprocess.Popen(command)
            return flask.render_template('task.html',
                                        mode="predict",
                                        pred_file=pred_file,
                                        task_name=task_name,
                                        full_cmd=" ".join(command))


def check_status(logs):
    if 'SUCCESS' in logs:
        return 0
    if 'ERROR' in logs:
        return -1
    return 1


def check_events(logs):
    lines = logs.split("\n")
    events = []
    progresses = []
    iteration = None
    hyperparams_json = None
    evaluation_json = None
    fdna_cmd = None
    fdna_progresses = []
    elapsed_time = None
    for l in lines:
        if '| Progress:' in l:
            progresses.append(l.strip())
            continue
        if '| EVENT:' in l:
            events.append(l.strip())
            continue
        if '| fastDNA | run:' in l:
            fdna_progresses.append(l.strip().split('| fastDNA | run: ')[-1])
            continue
        if '| fastDNA | cmd:' in l:
            fdna_cmd = l.strip().split('| fastDNA | cmd: ')[-1]
            continue
        if 'Iteration:' in l:
            iteration = l.strip().split(": ")[-1]
            continue
        if 'hyperparameters:' in l:
            valid_json = l.strip().split("hyperparameters: ")[-1].replace("'", "\"")
            hyperparams_json = json.loads(valid_json)
            hyperparams_json = {f"--{key}": [hypers_lookup[f"--{key}"], value] for key, value in hyperparams_json.items()}
            continue
        if 'evaluation:' in l:
            valid_json = l.strip().split("evaluation: ")[-1].replace("'", "\"")
            evaluation_json_temp = json.loads(valid_json)
            evaluation_json = defaultdict(dict)
            for key, value in evaluation_json_temp.items():
                if key != 'accordance':
                    n_top, tax_level = key.split("_")
                    evaluation_json[tax_level][n_top] = f"{round(float(value) * 100, 3)}"
                else:
                    evaluation_json[key] = f"{round(float(value), 4)}"
            continue
        if 'executed successfully in' in l:
            elapsed_time = ' '.join([elem for elem in l.strip().split(" ")[-3:] if not elem.startswith("0")])


    event_temp = events[-1].split(': ')[-1].split(" ") if events else None
    event = ' '.join(event_temp[:-1]) if event_temp else None
    event_id = int(event_temp[-1][1:-1]) if event_temp else None

    progress = progresses[-1].split(': ')[-1] if progresses else None

    if fdna_progresses:
        fdna_progress_tmp = fdna_progresses[-1]
        fdna_progress_tmp_split = re.split("\s+", fdna_progress_tmp)
        fdna_progress = {fdna_progress_tmp_split[i]: fdna_progress_tmp_split[i + 1] for i in range(0, len(fdna_progress_tmp_split) - 1, 2)} if fdna_progress_tmp_split else None
    else:
        fdna_progress = None


    return {'event': event,
            'event_id': event_id,
            'progress': progress,
            'iter': iteration,
            'hypers': hyperparams_json,
            'eval': evaluation_json,
            'elapsed_time': elapsed_time,
            'fastdna': {
                'cmd': fdna_cmd,
                'progress': fdna_progress
            },
            }


@app.route("/test/<id>")
def get_status(id):
    print(ptrs)

    ptr = ptrs[id]['ptr']
    status = 1
    with open(ptrs[id]['path'], "r+b") as f:
        mm = mmap.mmap(f.fileno(), 0)

        if ptr == 0:
            logs = str(mm[::], 'utf-8')
            ptr = len(mm)
            ptrs[id]['ptr'] = ptr
            return flask.jsonify({'content': logs, 'status': status})

        logs = str(mm[ptr:], 'utf-8')
        ptr = len(mm)

        status = check_status(logs)
        ptrs[id]['run_info'] = check_events(logs)
        ptrs[id]['ptr'] = ptr
    return flask.jsonify({'content': logs, 'status': status, 'run_info': ptrs[id]['run_info']})


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False, threaded=True)
