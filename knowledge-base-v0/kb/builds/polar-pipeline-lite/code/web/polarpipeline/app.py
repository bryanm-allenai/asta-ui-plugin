from flask import Flask, render_template, request, redirect, url_for, jsonify, send_file, send_from_directory
from datetime import datetime
import configparser
import urllib.parse
import ast
import svg
import os

app=Flask(__name__)

# The upstream app hardcodes Docker's /usr/src/app WORKDIR (set up by the
# project's Dockerfile, which copies web/ there). Running outside Docker,
# recompute the same "web/" directory so every path below still resolves.
APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def alphabetize(item):
    return item.lower()

base_path = '/input'
FIGURE_PRESETS_CONFIG = os.path.join(APP_ROOT, 'polarpipeline', 'assets', 'presets.ini')

@app.template_filter('urlencode')
def urlencode_filter(s):
    return urllib.parse.quote(str(s))

@app.template_filter('urldecode')
def urldecode_filter(s):
    return urllib.parse.unquote(s)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/filesearchbrowse/<path:path>')
@app.route('/filesearchbrowse/')
def filesearchbrowse(path=None):
    if path is None or not (path.startswith('input') or path.startswith('/input')):
        path = base_path

    path = APP_ROOT + '/' + path

    full_path = os.path.join('/', path)
    directory_listing = {}
    for item in os.listdir(full_path):
        is_dir = False
        if os.path.isdir(os.path.join(full_path, item)):
            is_dir = True
        directory_listing[item] = is_dir
    up_level_path = os.path.dirname(path)
    ordered_directory = sorted(os.listdir(full_path), key=alphabetize)
    return render_template('filesearchbrowse.html', current_path=full_path.replace(APP_ROOT + '/', ''), directory_listing=directory_listing, ordered_directory=ordered_directory, up_level_path=up_level_path)

def findHeaderLine(file):
    oldline = ''
    first = True
    for line in open(file):
        if first:
            oldline = line
            first = False
        if line.startswith('#'):
            oldline = line
        else:
            return oldline

@app.route('/filesearch/<path:path>')
def filesearch(path=None):
    header = findHeaderLine(f'{APP_ROOT}/{path}')
    delim = '\t'
    if path.endswith('.csv'):
        delim = ','
    return render_template('filesearch.html', path=path, columns=header.strip().split(delim))


@app.route('/filesearchbegin', methods=['POST'])
def filesearchbegin():
    searchname = f'{datetime.now().strftime("%Y-%m-%d_%H-%M-%S")}_filesearch_result.tsv'
    file = f'{APP_ROOT}/' + request.json.get("path")
    parameters = request.json.get("params")
    print(file, parameters, sep='\n')
    columnIndex = {}
    columnType = {}
    for param in parameters:
        columnType[param[0]] = int
    first = True
    header = ''
    bloat = findHeaderLine(file)
    # FIND DATA TYPES
    delim = '\t'
    if file.endswith('.csv'):
        delim = ','
    for row in open(file, 'r'):
        line = row.strip().split(delim)
        if first:
            if not bloat == row:
                continue

            first = False
            header = row
            for index, col in enumerate(line):
                if col in columnType:
                    columnIndex[col] = index
            continue
        if row == header: continue
        for col in columnIndex:
            value = line[columnIndex[col]]
            if value in ['-', '.']:
                value = ''
            if value == '':
                continue
            if columnType[col] == int:
                try:
                    int(value)
                    if '.' in value:
                        columnType[col] = float
                except:
                    try:
                        float(value)
                        columnType[col] = float
                    except:
                        columnType[col] = str
    #DO COMPARISONS
    command = f'rm -f {APP_ROOT}/polarpipeline/static/*_filesearch_result.tsv'
    os.system(command)
    with open(f'{APP_ROOT}/polarpipeline/static/{searchname}', 'w') as opened:
        opened.write(header)
        foundHeader = False
        for row in open(file, 'r'):
            if row == header:
                foundHeader = True
                continue
            if foundHeader == False:
                continue
            line = row.strip().split(delim)
            valid = True
            for param in parameters:
                col = param[0]
                bar = param[1]
                operator = param[2]
                nas = param[3]

                value = line[columnIndex[col]]
                if value in ['-', '.']:
                    value = ''

                if value == '' and nas:
                    continue
                match operator:
                    case '==':
                        if columnType[col](value) != columnType[col](bar):
                            valid = False
                    case '>=':
                        if columnType[col](value) < columnType[col](bar):
                            valid = False
                    case '<=':
                        if columnType[col](value) > columnType[col](bar):
                            valid = False
                    case '>':
                        if columnType[col](value) <= columnType[col](bar):
                            valid = False
                    case '<':
                        if columnType[col](value) >= columnType[col](bar):
                            valid = False
                    case '!=':
                        if columnType[col](value) == columnType[col](bar):
                            valid = False
                    case 'Contains':
                        if str(bar) not in str(value):
                            valid = False
            if valid:
                opened.write(row)
    return 'success'

@app.route('/filesearch/preview')
def filesearchpreview():
    static_dir = os.path.join(APP_ROOT, 'polarpipeline', 'static')
    file = ''
    for thing in os.listdir(static_dir):
        if thing.endswith('_filesearch_result.tsv'):
            file = os.path.join(static_dir, thing)
            break
    first = True
    filename = ''
    header = []
    filecontents = []
    for line in open(file):
        if first:
            first = False
            header = line.strip().split('\t')
            for col in header:
                if 'MERGED_' in col:
                    filename = col
            continue
        filecontents.append(line.strip().split('\t'))
        if len(filecontents) >= 50:
            return render_template('filesearchpreview.html', header=header, filecontents=filecontents, numlines=len(filecontents), filename=filename)

    return render_template('filesearchpreview.html', header=header, filecontents=filecontents)

@app.route('/filesearch/download')
def filesearchdownload():
    static_dir = os.path.join(APP_ROOT, 'polarpipeline', 'static')
    print('in download')
    filename=''
    print(os.listdir(static_dir))
    for file in os.listdir(static_dir):
        if file.endswith('_filesearch_result.tsv'):
            filename = os.path.join(static_dir, file)
    return send_file(filename, as_attachment=True)

@app.route('/figuregenerator')
def figuregenerator():
    return render_template('figuregenerator.html')

def save_preset(preset_name, preset_vals):
    config = configparser.ConfigParser()
    config.read(FIGURE_PRESETS_CONFIG)

    if not config.has_section(preset_name):
        config.add_section(preset_name)

    for key, value in preset_vals.items():
        value = str(value)  # Convert other data types to strings

        config.set(preset_name, key, value)

    with open(FIGURE_PRESETS_CONFIG, 'w') as configfile:
        config.write(configfile)

@app.route('/saveState', methods=['POST'])
def saveState():
    preset_name = request.json.get("presetname")
    homo = request.json.get("homo")
    abproteinname = request.json.get("abproteinname")
    proteinname = request.json.get("proteinname")
    if homo == True:
        homolen = request.json.get("homolen")
        homostructures = request.json.get("homostructures")
        homofeatures = request.json.get("homofeatures")

        preset_vals = {
            "homo": homo,
            "abproteinname": abproteinname,
            "proteinname": proteinname,
            "homolen": homolen,
            "homostructures": homostructures,
            "homofeatures": homofeatures
        }

    else:
        leftlen = request.json.get("leftlen")
        leftstructures = request.json.get("leftstructures")
        rightlen = request.json.get("rightlen")
        rightstructures = request.json.get("rightstructures")
        leftfeatures = request.json.get("leftfeatures")
        rightfeatures = request.json.get("rightfeatures")

        preset_vals = {
            "homo": homo,
            "abproteinname": abproteinname,
            "proteinname": proteinname,
            "leftlen": leftlen,
            "leftstructures": leftstructures,
            "rightlen": rightlen,
            "rightstructures": rightstructures,
            "leftfeatures": leftfeatures,
            "rightfeatures": rightfeatures
        }

    save_preset(str(preset_name), preset_vals)

    response_data = {
        "message": "Data received successfully"
    }

    return jsonify(response_data)

def load_presets():
    config = configparser.ConfigParser()
    config.read(FIGURE_PRESETS_CONFIG)
    return config.sections()

@app.route('/loadStates', methods=['POST'])
def loadStates():
    presets = load_presets()
    response_data = {
        "data": presets
    }

    return jsonify(response_data)

def load_preset(section_name):
    config = configparser.ConfigParser()
    config.read(FIGURE_PRESETS_CONFIG)
    if section_name in config:
        return parse_config_dict(config[section_name])
    else:
        return None  # Section not found

def parse_config_dict(config_section):
    parsed_data = {}
    for key, value in config_section.items():
        try:
            # Attempt to evaluate the value as literal Python expression
            parsed_value = ast.literal_eval(value)
            if isinstance(parsed_value, list):
                parsed_data[key] = parsed_value
            else:
                parsed_data[key] = parsed_value
        except (SyntaxError, ValueError):
            # If evaluation fails, store the value as is
            parsed_data[key] = value
    return parsed_data

@app.route('/loadState', methods=['POST'])
def loadState():
    preset = request.json.get('preset')

    preset_data = load_preset(preset)
    print(preset_data)

    response_data = {
        "data": preset_data
    }

    return jsonify(response_data)

def customsortfeatures(feature):
    num = -int(feature[1])
    return num

@app.route('/generatefigure', methods=['POST'])
def generatefigure():
    homo = request.json.get("homo")
    abproteinname = request.json.get("abproteinname")
    proteinname = request.json.get("proteinname")

    print(proteinname)
    print(abproteinname)

    topbar = []
    bottombar = []
    leftfeatureelements = []
    rightfeatureelements = []
    homobar = []
    homofeatureelements = []

    base = [
        svg.Rect( # BACKGROUND
            fill="white",
            x=0,
            y=0,
            width=480*2,
            height=480
        ),
        svg.Text( # PROTEIN NAME
            text=f'{abproteinname} | {proteinname}',
            x=5,
            y=45,
            fill="black",
            font_family="Sans,Arial",
            font_weight="bold",
            font_size="30",
            font_stretch="ultra-condensed"
        ),
    ]

    if not homo:
        leftlen = request.json.get("leftlen")
        leftstructures = request.json.get("leftstructures")
        rightlen = request.json.get("rightlen")
        rightstructures = request.json.get("rightstructures")
        leftfeatures = request.json.get("leftfeatures")
        rightfeatures = request.json.get("rightfeatures")

        maxlen = max(int(leftlen), int(rightlen))

        base.append(svg.Line( # FIRST LINE
            stroke_width=5,
            stroke="grey",
            x1=50,
            y1=200,
            x2=50+((int(leftlen)/maxlen) * 550) + ((1/maxlen) * 550),
            y2=200
        ))
        base.append(svg.Line( # SECOND LINE
            stroke_width=5,
            stroke="grey",
            x1=50,
            y1=360,
            x2=50+((int(rightlen)/maxlen) * 550) + ((1/maxlen) * 550),
            y2=360
        ))
        base.append(svg.Text( # 0|1 TEXT
            text='0|1',
            x=5,
            y=205,
            fill="black",
            font_family="monospace",
            stroke_width=1,
            font_size=20
        ))
        base.append(svg.Text( # 1|0 TEXT
            text='1|0',
            x=5,
            y=365,
            fill="black",
            font_family="monospace",
            stroke_width=1,
            font_size=20
        ))
        base.append(svg.Text( # TOP AA LENGTH
            text=f'{leftlen} AA',
            x=50+((int(leftlen)/maxlen) * 550) + ((1/maxlen) * 550) + 10,
            y=205,
            fill="black",
            font_family="monospace",
            stroke_width=1,
            font_size=20
        ))
        base.append(svg.Text( # BOTTOM AA LENGTH
            text=f'{rightlen} AA',
            x=50+((int(rightlen)/maxlen) * 550) + ((1/maxlen) * 550) + 10,
            y=365,
            fill="black",
            font_family="monospace",
            stroke_width=1,
            font_size=20
        ))

        for item in leftstructures:
            if len(item) != 4: continue
            fontsize = 20
            if (len(item[0]) * fontsize * (3/5)) > (((int(item[2])-int(item[1]))/maxlen)*550):
                fontsize = (((((int(item[2])-int(item[1]))/maxlen)*550) * 0.9) / (3/5)) / len(item[0])
            topbar.append(
                svg.Rect(
                    fill=item[3],
                    x=50+((int(item[1])/maxlen)*550),
                    y=185,
                    width=(((int(item[2])-int(item[1]))/maxlen)*550),
                    height=30,
                )
            )
            fontcol = "black"
            if item[0] == "DEGEN": fontcol="red"
            print(50+((int(item[1])+int(item[2]))/2))
            topbar.append(
                svg.Text(
                    text=item[0],
                    x=50+((((int(item[1])+int(item[2]))/2)/maxlen)*550)-(fontsize*(3/5)*len(item[0])/2),
                    y=205,
                    fill=fontcol,
                    font_family="monospace",
                    font_size=fontsize
                )
            )

        for item in rightstructures:
            if len(item) != 4: continue
            fontsize = 20
            if (len(item[0]) * fontsize * (3/5)) > (((int(item[2])-int(item[1]))/maxlen)*550):
                fontsize = (((((int(item[2])-int(item[1]))/maxlen)*550) * 0.9) / (3/5)) / len(item[0])
            bottombar.append(
                svg.Rect(
                    fill=item[3],
                    x=50+((int(item[1])/maxlen)*550),
                    y=345,
                    width=(((int(item[2])-int(item[1]))/maxlen)*550),
                    height=30,
                )
            )
            fontcol = "black"
            if item[0] == "DEGEN": fontcol="red"
            bottombar.append(
                svg.Text(
                    text=item[0],
                    x=50+((((int(item[1])+int(item[2]))/2)/maxlen)*550)-(fontsize*(3/5)*len(item[0])/2),
                    y=365,
                    fill=fontcol,
                    font_family="monospace",
                    font_size=fontsize
                )
            )

        leftfeaturestemp = sorted([x for x in leftfeatures if x], key=customsortfeatures)
        leftfeatureswithoverlap = []
        for i in range(len(leftfeaturestemp)):
            height = 0
            if '^' in leftfeaturestemp[i][0]:
                height = (len(leftfeaturestemp[i][0].split('^'))-1)*30
            leftfeatureswithoverlap.append(leftfeaturestemp[i]+[height])
            print(leftfeatureswithoverlap)
        for item in leftfeatureswithoverlap:
            leftfeatureelements.append(
                svg.Line(
                    stroke_width=3,
                    stroke="red",
                    x1=50+((int(item[1])/maxlen) * 550),
                    y1=185,
                    x2=50+((int(item[1])/maxlen) * 550),
                    y2=155-item[2]
                )
            )
            leftfeatureelements.append(
                svg.Text(
                    text=item[0].replace('^', ''),
                    x=50 + ((int(item[1]) / maxlen) * 550) + 6,
                    y=170-item[2],
                    font_family="monospace",
                    font_size=20
                )
            )

        rightfeaturestemp = sorted([x for x in rightfeatures if x], key=customsortfeatures)
        rightfeatureswithoverlap = []
        for i in range(len(rightfeaturestemp)):
            height = 0
            if '^' in rightfeaturestemp[i][0]:
                height = (len(rightfeaturestemp[i][0].split('^'))-1)*30
            rightfeatureswithoverlap.append(rightfeaturestemp[i]+[height])
            print(rightfeatureswithoverlap)
        for item in rightfeatureswithoverlap:
            rightfeatureelements.append(
                svg.Line(
                    stroke_width=3,
                    stroke="red",
                    x1=50+((int(item[1])/maxlen) * 550),
                    y1=345,
                    x2=50+((int(item[1])/maxlen) * 550),
                    y2=315-item[2]
                )
            )
            rightfeatureelements.append(
                svg.Text(
                    text=item[0].replace('^', ''),
                    x=50 + ((int(item[1]) / maxlen) * 550) + 6,
                    y=330-item[2],
                    font_family="monospace",
                    font_size=20
                )
            )
    else:
        homolen = request.json.get("homolen")
        homostructures = request.json.get("homostructures")
        homofeatures = request.json.get("homofeatures")

        base.append(svg.Line( # SECOND LINE
            stroke_width=5,
            stroke="grey",
            x1=50,
            y1=280,
            x2=50+((int(homolen)/int(homolen)) * 550) + ((1/int(homolen)) * 550),
            y2=280
        ))
        base.append(svg.Text( # 1|1 TEXT
            text='1|1',
            x=5,
            y=285,
            fill="black",
            font_family="monospace",
            stroke_width=1,
            font_size=20
        ))
        base.append(svg.Text( # TOP AA LENGTH
            text=f'{homolen} AA',
            x=50+((int(homolen)/int(homolen)) * 550) + ((1/int(homolen)) * 550) + 10,
            y=285,
            fill="black",
            font_family="monospace",
            stroke_width=1,
            font_size=20
        ))
        for item in homostructures:
            if len(item) != 4: continue
            fontsize = 20
            if (len(item[0]) * fontsize * (3/5)) > (((int(item[2])-int(item[1]))/int(homolen))*550):
                fontsize = (((((int(item[2])-int(item[1]))/int(homolen))*550) * 0.9) / (3/5)) / len(item[0])
            homobar.append(
                svg.Rect(
                    fill=item[3],
                    x=50+((int(item[1])/int(homolen))*550),
                    y=265,
                    width=(((int(item[2])-int(item[1]))/int(homolen))*550),
                    height=30,
                )
            )
            fontcol = "black"
            if item[0] == "DEGEN": fontcol="red"
            homobar.append(
                svg.Text(
                    text=item[0],
                    x=50+((((int(item[1])+int(item[2]))/2)/int(homolen))*550)-(fontsize*(3/5)*len(item[0])/2),
                    y=285,
                    fill=fontcol,
                    font_family="monospace",
                    font_size=fontsize
                )
            )
            homofeaturestemp = sorted([x for x in homofeatures if x], key=customsortfeatures)
            homofeatureswithoverlap = []
            for i in range(len(homofeaturestemp)):
                height = 0
                if '^' in homofeaturestemp[i][0]:
                    height = (len(homofeaturestemp[i][0].split('^'))-1)*30
                homofeatureswithoverlap.append(homofeaturestemp[i]+[height])
                print(homofeatureswithoverlap)
            for item in homofeatureswithoverlap:
                homofeatureelements.append(
                    svg.Line(
                        stroke_width=3,
                        stroke="red",
                        x1=50+((int(item[1])/int(homolen)) * 550),
                        y1=265,
                        x2=50+((int(item[1])/int(homolen)) * 550),
                        y2=235-item[2]
                    )
                )
                homofeatureelements.append(
                    svg.Text(
                        text=item[0],
                        x=50 + ((int(item[1]) / int(homolen)) * 550) + 6,
                        y=250-item[2],
                        font_family="monospace",
                        font_size=20
                    )
                )

        # print(homolen)
        # print(homostructures)
        # print(homofeatures)

    canvas = svg.SVG(
        width=480*2,
        height=480,
        elements = base + topbar + bottombar + homobar + leftfeatureelements + rightfeatureelements + homofeatureelements
    )

    svg_string = str(canvas)
    with open(os.path.join(APP_ROOT, 'polarpipeline', 'static', 'variantFig.svg'), 'w') as opened:
        opened.write(svg_string)

    response_data = {
        "message": "Data received successfully"
    }

    return jsonify(response_data)

@app.route('/downloadfigure')
def downloadfigure():
    try:
        # Build the path to the image file in the static folder
        image_path = os.path.join(APP_ROOT, 'polarpipeline', 'static', 'variantFig.svg')

        # Use Flask's send_file function to send the image as a download
        return send_file(image_path, as_attachment=True)

    except FileNotFoundError:
        # Handle the case where the image file is not found
        return "Image not found", 404
