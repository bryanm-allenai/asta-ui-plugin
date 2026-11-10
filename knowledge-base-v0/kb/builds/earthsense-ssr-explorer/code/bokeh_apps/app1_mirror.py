"""
Exploration of FORTH-RTM SSR changes,  its causes and the possible links with other climate variables. PhD Thesis: https://www.didaktorika.gr/eadd/handle/10442/59941
Creator: Michael Stamatis, email: [email removed]
"""

from bokeh.layouts import row, column
from bokeh import events
from bokeh.plotting import figure, curdoc
from bokeh.models import (
    InlineStyleSheet,
    ColorBar,
    TapTool,
    BoxSelectTool,
    ColumnDataSource,
    CustomJS,
    LinearColorMapper,
    HoverTool,
    Div,
    DatetimeTickFormatter,
    TextAreaInput,
    DatetimeTickFormatter,
    CrosshairTool,
    HoverTool,
    Span,
    FreehandDrawTool,
)
from bokeh.palettes import interp_palette
import numpy as np, pandas as pd, xarray as xr, scipy as sp
from scipy.signal import savgol_filter
import base64
from scipy.interpolate import UnivariateSpline

colorss = [
    "rgb(16, 94, 0)",
    "rgb(0, 185, 9)",
    "rgb(0, 255, 64)",
    "rgb(0, 28, 121)",
    "rgb(0, 60, 255)",
    "rgb(0, 200, 255)",
    "rgb(255, 230, 0)",
    "rgb(218, 116, 0)",
    "#000000",
    "rgb(111, 2, 161)",
    "#ff35a4",
    "rgb(255, 0, 0)",
]
curdoc().theme = "dark_minimal"

p9 = {"active_scroll": "wheel_zoom"}


def add_extras(p, drawline_width=5, drawalpha=0.4, drawcolor="red", cross=1):
    # box edit tool wants to be first
    # global sourcebox
    # sourcebox = ColumnDataSource( data=dict( x=[0], y=[0], width=[0], height=[0], color=['grey'], alpha=[0.35], ), default_values = dict( color="grey", alpha=0.35, ), )
    # rbox = p.rect("x", "y", "width", "height", color="color", alpha="alpha", source=sourcebox)
    # box_tool = BoxEditTool(renderers=[rbox],)
    # p.add_tools(box_tool)

    # draw tool
    rdraw = p.multi_line(
        [], [], line_width=drawline_width, alpha=drawalpha, color=drawcolor
    )
    draw_tool = FreehandDrawTool(renderers=[rdraw], num_objects=100)
    p.add_tools(draw_tool)

    p.add_tools("lasso_select", "tap")
    p.toolbar.logo = None
    p.toolbar.autohide = True

    Span_height = Span(
        dimension="height", line_dash="dashed", line_width=2, line_color="#878787"
    )
    Crosshair_Tool = CrosshairTool(overlay=Span_height)
    if cross == 1:
        p.add_tools(Crosshair_Tool)

    # re-arange y axis when hide a glyph! not works if i set the y_range
    # p.y_range.only_visible = True


def crd():
    import cartopy.feature as cf, numpy as np

    # create the list of coordinates separated by nan to avoid connecting the lines
    x_coords = []
    y_coords = []
    for coord_seq in cf.COASTLINE.geometries():
        x_coords.extend([k[0] for k in coord_seq.coords] + [np.nan])
        y_coords.extend([k[1] for k in coord_seq.coords] + [np.nan])

    # x_coords2 = []
    # y_coords2 = []
    # for coord_seq in cf.BORDERS.geometries():
    #     x_coords2.extend([k[0] for k in coord_seq.coords] + [np.nan])
    #     y_coords2.extend([k[1] for k in coord_seq.coords] + [np.nan])
    return (
        x_coords,
        y_coords,
    )  # x_coords2,y_coords2


x_coords, y_coords = [i for i in crd()]
tais = InlineStyleSheet(
    css=""" /* Outer container styling */ :host { background: #181824 !important; border-radius: 14px !important; padding: 16px !important; box-shadow: 0 4px 18px #0006 !important; } /* Title label styling */ :host .bk-input-group label, :host .bk-textinput-title { color: #34ffe0 !important; font-size: 1.14em !important; font-family: 'Fira Code', monospace !important; font-weight: bold !important; margin-bottom: 12px !important; letter-spacing: 0.5px !important; text-shadow: 0 2px 12px #34ffe077, 0 1px 3px #222 !important; } /* The textarea input box - changed from input[type="text"] to textarea */ :host textarea { background: #23233c !important; color: #f9fafb !important; border: 2px solid #06b6d4 !important; border-radius: 8px !important; padding: 11px 15px !important; font-size: 1.08em !important; font-family: 'Fira Code', monospace !important; transition: border 0.12s ease, box-shadow 0.12s ease !important; box-shadow: none !important; resize: vertical !important; min-height: 120px !important; } /* On hover/focus: red border with glowing effect */ :host textarea:hover, :host textarea:focus { border-color: #ff3049 !important; box-shadow: 0 0 0 2px #ff304999, 0 0 15px #ff3049bb !important; outline: none !important; } /* Placeholder text */ :host textarea::placeholder { color: #9ca3af !important; opacity: 0.7 !important; font-style: italic !important; } /* Scrollbar styling for webkit browsers */ :host textarea::-webkit-scrollbar { width: 8px !important; } :host textarea::-webkit-scrollbar-track { background: #1a1a2e !important; border-radius: 4px !important; } :host textarea::-webkit-scrollbar-thumb { background: #06b6d4 !important; border-radius: 4px !important; } :host textarea::-webkit-scrollbar-thumb:hover { background: #ff3049 !important; } """
)
#########################
# ----- MY DATA ------- #
#########################

# p1: GDB
fmc_ssr = xr.open_dataset(
    "data/FMCX_8418_SurfaceDown_f.nc"
)["SurfaceDown"].sel(time=slice("1984-01-01", "2018-12-31"))
gdbdc = (
    xr.open_dataset(
        "data/__anom_8418_slopes_FMCX8418_SurfaceDown_.nc"
    )["slope"].rename("GDB")
    * 120
)

# p2: CONTRIBUTIONS
a1 = xr.open_dataset(
    "data/contributions_all_1984-2018_.nc"
).fillna(0)
a1["sumcon"] = (
    a1.AC1
    + a1.AC2
    + a1.AC3
    + a1.TAU1
    + a1.TAU2
    + a1.TAU3
    + a1.AOD
    + a1.SSA
    + a1.ASYM
    + a1.H2O
    + a1.O3
)
a2 = a1.transpose("lon", "lat")
lisa = ["AC1", "AC2", "AC3", "TAU1", "TAU2", "TAU3", "AOD", "SSA", "ASYM", "H2O", "O3"]

# p3: DRIVERS
we1 = xr.open_dataset(
    "data/FMCX_8418_drivers_we1.nc"
).fillna(0)

# p4: CLIMATIC IMPACTS
impac1 = xr.open_dataset(
    "data/FMCX_8418_impac1.nc"
).fillna(0)


#########################
# ------ The App ------ #
#########################

# p1) GDB
latitudes = fmc_ssr.lat.values.tolist()
longitudes = fmc_ssr.lon.values.tolist()
lati = np.repeat(latitudes, len(longitudes))
loni = np.tile(longitudes, len(latitudes))
s1 = ColumnDataSource(
    data={"image": [gdbdc.values], "latitudes": [lati], "longitudes": [loni]}
)

# Set up Bokeh figure
p1 = figure(
    output_backend="webgl",
    border_fill_color="#2d2d2d",
    background_fill_color="#2d2d2d",
    width=845,
    min_border_bottom=10,
    min_border_right=80,
    toolbar_location="below",
    height=445,
    x_range=(min(longitudes), max(longitudes)),
    y_range=(min(latitudes), max(latitudes)),
    title=r"$$FMC-RTM~GDB, 1984-2018$$",
    **p9,
    styles={
        "margin-top": "12px",
        "margin-left": "-848px",
        "padding": "0px",
        "border-radius": "10px",
        "background-color": "#2d2d2d",
    },
)
p1_ = figure(
    width=850,
    height=450,
    styles={
        "margin-top": "10px",
        "margin-left": "10px",
        "border-radius": "10px",
        "padding": "15px",
        "box-shadow": "0 3px 3px #fcc020",
        "background-color": "#2d2d2d",
    },
)
p1_.border_fill_color = "#2d2d2d"
p1_.toolbar_location = None

mike2 = (
    "#000063",
    "#123aff",
    "#00aeff",
    "#26fff4",
    "#00ff95",
    "#ffffff",
    "#ffff00",
    "#ff8a15",
    "#ff2a1b",
    "#db0000",
    "#4b0000",
)
bo_mike2 = interp_palette(mike2, 255)

color_mapper = LinearColorMapper(palette=bo_mike2, low=-15, high=15)
color_bar = ColorBar(
    color_mapper=color_mapper,
    location=(0, 0),
    title=r"$$Wm^{-2}decade{-1}$$",
    title_standoff=1,
    title_text_baseline="middle",
    title_text_align="right",
    background_fill_alpha=0,
)
p1.add_layout(color_bar, "right")

# # Add custom text (label) at specific (x, y) coordinates
# label = Label( text=r"$$Wm^{-2}decade^{-1}$$", x=150, y=130, x_units="screen", y_units="screen", )
# p1.add_layout(label)

# Display the temperature data using the image renderer
p11 = p1.image(
    image="image",
    color_mapper=color_mapper,
    x=min(longitudes),
    y=min(latitudes),
    dw=max(longitudes) - min(longitudes),
    dh=max(latitudes) - min(latitudes),
    source=s1,
)
p12 = p1.line(x=x_coords, y=y_coords, line_width=1, line_color="black")
sourcebox = ColumnDataSource(
    data=dict(
        x=[],
        y=[],
        width=[],
        height=[],
        color=["grey"],
        alpha=[0.35],
    ),
    default_values=dict(
        color="grey",
        alpha=0.35,
    ),
)
rbox = p1.rect(
    "x", "y", "width", "height", color="color", alpha="alpha", source=sourcebox
)
box_tool = BoxSelectTool(persistent=True)
p1.add_tools(box_tool)


p1.add_tools(
    HoverTool(
        tooltips="""<div style="background-color: #f0f0f0; padding: 5px; border-radius: 5px; box-shadow: 0px 0px 5px rgba(0,0,0,0.3);">        <font size="3" style="background-color: #f0f0f0; padding: 5px; border-radius: 5px;">
            <i>Lon:</i> <b>@longitudes{0.000}<sup>o</sup></b> <br> 
            <i>Lat:</i> <b>@latitudes{0.000}<sup>o</sup></b> <br>
            <i>GDB:</i> <b>@image{0.000} Wm<sup>-2</sup></b> <br>
        </font> </div> <style> :host { --tooltip-border: transparent;  /* Same border color used everywhere */ --tooltip-color: transparent; --tooltip-text: #2f2f2f;} </style> """,
        mode="mouse",
        renderers=[p11],
    )
)

add_extras(p1, cross=0)

tap_tool = p1.select(type=TapTool)
tap_tool.mode = "replace"


# p2) bar plot
xdates = pd.date_range("1984", "2018", freq="YS")
variables = [
    "AC1",
    "AC2",
    "AC3",
    "COT1",
    "COT2",
    "COT3",
    "AOD",
    "SSA",
    "ASYM",
    "H2O",
    "O3",
    "GDB",
]

s2 = ColumnDataSource(
    data=dict(x=[], y=[], colors=colorss, hatch_pattern=[""] * 11 + ["@"])
)
p2 = figure(
    width=600,
    height=450,
    title=r"$$Contribution~to~GDB$$",
    x_range=variables,
    **p9,
    y_axis_label=r"$$Wm^{-2}decade^{-1}$$",
    border_fill_color="#2d2d2d",
    background_fill_color="#2d2d2d",
    min_border_bottom=70,
    min_border_top=20,
    min_border_right=50,
    toolbar_location="below",
    styles={
        "margin-top": "9px",
        "margin-left": "10px",
        "padding": "15px",
        "border-radius": "10px",
        "box-shadow": "0 3px 3px #fcc020",
        "background-color": "#2d2d2d",
    },
)
p22 = p2.vbar(
    x="x",
    top="y",
    source=s2,
    color="colors",
    hatch_pattern="hatch_pattern",
    hatch_color="yellow",
    hover_line_color="red",
    hover_line_width=5,
    line_width=2,
    width=0.7,
    border_radius=5,
    line_color="black",
)
p2.add_tools(
    HoverTool(
        tooltips="""<div style="background-color: #f0f0f0; padding: 5px; border-radius: 5px; box-shadow: 0px 0px 5px rgba(0,0,0,0.3);">        <font size="3" style="background-color: #f0f0f0; padding: 5px; border-radius: 5px;">
                       <b>@x</b> <br> 
                       <i>Con:</i> <b>@y{0.00}</b> <br> 
        </font> </div> <style> :host { --tooltip-border: transparent;  /* Same border color used everywhere */ --tooltip-color: transparent; --tooltip-text: #2f2f2f;} </style> """,
        mode="mouse",
        show_arrow=False,
        renderers=[p22],
    )
)
add_extras(p2, cross=0)
p2.xgrid.grid_line_color = None
# p3) The Drivers
s3 = ColumnDataSource(
    data=dict(
        x=[],
        AC1=[],
        AC2=[],
        AC3=[],
        COT1=[],
        COT2=[],
        COT3=[],
        AOD=[],
        SSA=[],
        ASYM=[],
        H2O=[],
        O3=[],
        SSR=[],
        AC1x=[],
        AC2x=[],
        AC3x=[],
        COT1x=[],
        COT2x=[],
        COT3x=[],
        AODx=[],
        SSAx=[],
        ASYMx=[],
        H2Ox=[],
        O3x=[],
        SSRx=[],
    )
)
p3 = figure(
    width=1000,
    height=450,
    x_axis_type="datetime",
    x_range=(pd.Timestamp("1984"), pd.Timestamp("2018")),
    border_fill_color="#2d2d2d",
    background_fill_color="#2d2d2d",
    y_range=(-3, 3),
    min_border_bottom=70,
    min_border_right=140,
    toolbar_location="below",
    title=r"$$GDB~Drivers$$",
    y_axis_label=r"$$Normalized~SG~filtered~data$$",
    **p9,
    styles={
        "margin-top": "10px",
        "margin-left": "13px",
        "padding": "15px",
        "border-radius": "10px",
        "box-shadow": "0 3px 3px #fcc020",
        "background-color": "#2d2d2d",
    },
)
p33 = p3.line(
    "x", "AC1", source=s3, line_alpha=0, line_width=0
)  # p3.circle('x', 'AC1', source=s3, color='blue',size=0)
p3.xaxis[0].formatter = DatetimeTickFormatter(years="%Y")

s3list = [
    "AC1",
    "AC2",
    "AC3",
    "COT1",
    "COT2",
    "COT3",
    "AOD",
    "SSA",
    "ASYM",
    "H2O",
    "O3",
    "SSR",
]
for kk in range(12):
    p3.line(
        "x",
        s3list[kk],
        legend_label=s3list[kk],
        source=s3,
        color=colorss[kk],
        line_width=5,
    )
    # p3.circle('x', s3list[kk],legend_label=s3list[kk], source=s3, color=colorss[kk],size=10)

p3.add_tools(
    HoverTool(
        tooltips="""<div style="background-color: #f0f0f0; padding: 5px; border-radius: 5px; box-shadow: 0px 0px 5px rgba(0,0,0,0.3);">        <font size="3" style="background-color: #f0f0f0; padding: 5px; border-radius: 5px;">
            <i>year:</i> <b>@x{%Y}</b> <br> 
            <i>AC1:</i> <b>@AC1x{0.0000}</b> <br>
            <i>AC2:</i> <b>@AC2x{0.0000}</b> <br>
            <i>AC3:</i> <b>@AC3x{0.0000}</b> <br>
            <i>COT1:</i> <b>@COT1x{0.0000}</b> <br>
            <i>COT2:</i> <b>@COT2x{0.0000}</b> <br>
            <i>COT3:</i> <b>@COT3x{0.0000}</b> <br>
            <i>AOD:</i> <b>@AODx{0.0000}</b> <br>
            <i>SSA:</i> <b>@SSAx{0.0000}</b> <br>
            <i>ASYM:</i> <b>@ASYMx{0.0000}</b> <br>
            <i>H2O:</i> <b>@H2Ox{0.0000}</b> <br>
            <i>O3:</i> <b>@O3x{0.0000} DU</b> <br>
            <i>SSR:</i> <b>@SSRx{0.00} Wm<sup>-2</sup></b> <br>
        </font> </div> <style> :host { --tooltip-border: transparent;  /* Same border color used everywhere */ --tooltip-color: transparent; --tooltip-text: #2f2f2f;} </style> """,
        formatters={"@x": "datetime"},
        mode="vline",
        attachment="left",
        show_arrow=False,
        renderers=[p33],
    )
)
add_extras(p3)
p3.legend.location = "center"
p3.add_layout(p3.legend[0], "right")
p3.legend.click_policy = "hide"
p3.legend.inactive_fill_color = "grey"

# p4) The Climpacts
climcolor = [
    "rgb(255, 230, 0)",
    "rgb(0, 85, 255)",
    "#000000",
    "#17f200",
    "#ff35a4",
    "#949191",
    "rgb(255, 0, 0)",
]
s4 = ColumnDataSource(
    data=dict(
        x=[],
        Temperature=[],
        Precipitation=[],
        Evaporation=[],
        Snow_Evaporation=[],
        Snow_Density=[],
        Sea_Ice_Fraction=[],
        SSR=[],
        Temperaturex=[],
        Precipitationx=[],
        Evaporationx=[],
        Snow_Evaporationx=[],
        Snow_Densityx=[],
        Sea_Ice_Fractionx=[],
        SSRx=[],
    )
)
p4 = figure(
    width=750,
    height=450,
    x_axis_type="datetime",
    x_range=(pd.Timestamp("1984"), pd.Timestamp("2018")),
    min_border_bottom=0,
    min_border_right=40,
    toolbar_location="below",
    border_fill_color="#2d2d2d",
    background_fill_color="#2d2d2d",
    y_range=(-3, 3),
    title=r"$$Climatic~Variables~and~GDB$$",
    y_axis_label=r"$$Normalized~SG~filtered~data$$",
    **p9,
    styles={
        "margin-top": "9px",
        "margin-left": "10px",
        "padding": "15px",
        "border-radius": "10px",
        "box-shadow": "0 3px 3px #fcc020",
        "background-color": "#2d2d2d",
    },
)
p44 = p4.line(
    "x", "Temperature", source=s4, line_alpha=0, line_width=0
)  # p4.circle('x', 'Temperature', source=s4, color='red',size=0)
p4.xaxis[0].formatter = DatetimeTickFormatter(years="%Y")

s4list = [
    "Temperature",
    "Precipitation",
    "Evaporation",
    "Snow_Evaporation",
    "Snow_Density",
    "Sea_Ice_Fraction",
    "SSR",
]
s4listlegend = ["Temp", "Prec", "Evap", "SnowEva", "SnowDen", "SeaIce", "SSR"]

for kk in range(7):
    p4.line(
        "x",
        s4list[kk],
        legend_label=s4listlegend[kk],
        source=s4,
        color=climcolor[kk],
        line_width=5,
    )
    # p4.circle('x',s4list[kk],legend_label=s4list[kk], source=s4, color=climcolor[kk],size=10)


p4.add_tools(
    HoverTool(
        tooltips="""<div style="background-color: #f0f0f0; padding: 5px; border-radius: 5px; box-shadow: 0px 0px 5px rgba(0,0,0,0.3);">        <font size="3" style="background-color: #f0f0f0; padding: 5px; border-radius: 5px;">
            <b>Annual Anomalies<br> (1984-2018)</b><br>
            <i>year:</i> <b>@x{%Y}</b> <br> 
            <i>Temp:</i> <b>@Temperaturex{0.0000} K</b> <br>
            <i>Prec:</i> <b>@Precipitationx{0.0000000} m</b> <br>
            <i>Evap:</i> <b>@Evaporationx{0.0000000} m</b> <br>
            <i>SnowEvap:</i> <b>@Snow_Evaporationx{0.0000000} m</b> <br>
            <i>SnowDen:</i> <b>@Snow_Densityx{0.0000000} Kgm<sup>-3</sup></b> <br>
            <i>SeaIce:</i> <b>@Sea_Ice_Fractionx{0.0000000}</b> <br>
            <i>SSR:</i> <b>@SSRx{0.00} Wm<sup>-2</sup></b> <br>
        </font> </div> <style> :host { --tooltip-border: transparent;  /* Same border color used everywhere */ --tooltip-color: transparent; --tooltip-text: #2f2f2f;} </style> """,
        formatters={"@x": "datetime"},
        mode="vline",
        attachment="left",
        show_arrow=False,
        renderers=[p44],
    )
)
add_extras(p4)


p4.legend.location = "right"
p4.add_layout(p4.legend[0], "above")
p4.legend.click_policy = "hide"
p4.legend.inactive_fill_color = "grey"
p4.legend.orientation = "horizontal"


# p5

from datetime import date
from random import randint

from bokeh.io import show
from bokeh.models import (
    ColumnDataSource,
    DataTable,
    DateFormatter,
    TableColumn,
    InlineStyleSheet,
    HTMLTemplateFormatter,
)

data5 = dict(
    Parameters=[
        "AC1",
        "AC2",
        "AC3",
        "COT1",
        "COT2",
        "COT3",
        "AOD",
        "SSA",
        "ASYM",
        "H2O",
        "O3",
        "SSR",
        "Temp",
        "Prec",
        "Evap",
        "SnowEva",
        "SnowDen",
        "SeaIce",
    ],
    Pearson_R=["-"] * 18,
    Spearman_R=["-"] * 18,
    Change=["-"] * 18,
    Pval_95=["-"] * 18,
)
template0 = """
            <div style="color:<%= 
                (function colorfromint(){
                    if(Math.abs(Pearson_R) >= 0.6 || Math.abs(Spearman_R) >= 0.6){
                        return("red")}
                    }()) %>; 
                "> 
            <%= value %>
            </div>
            """
formatter0 = HTMLTemplateFormatter(template=template0)

template01 = """
            <div style="color:<%= 
                (function colorfromint(){
                    if(Math.abs(Pearson_R) >= 0.6){
                        return("red")}
                    }()) %>; 
                "> 
            <%= value %>
            </div>
            """
formatter01 = HTMLTemplateFormatter(template=template01)


template02 = """
            <div style="color:<%= 
                (function colorfromint(){
                    if(Math.abs(Spearman_R) >= 0.6){
                        return("red")}
                    }()) %>; 
                "> 
            <%= value %>
            </div>
            """
formatter02 = HTMLTemplateFormatter(template=template02)

template03 = """
            <div style="color:<%= 
                (function colorfromint(){
                    if(Pval_95 <= 0.05 && Math.sign(Change) == 1){
                        return("green")}
                    else if(Pval_95 <= 0.05 && Math.sign(Change) == -1){
                        return("orange")}
                    }()) %>; 
                "> 
            <%= value %>
            </div>
            """
formatter03 = HTMLTemplateFormatter(template=template03)


source5 = ColumnDataSource(data5)
columns5 = [
    TableColumn(
        field="Parameters",
        formatter=formatter0,
        title="Parameters",
    ),
    TableColumn(
        field="Pearson_R",
        formatter=formatter01,
        title="Pearson_R",
    ),
    TableColumn(
        field="Spearman_R",
        formatter=formatter02,
        title="Spearman_R",
    ),
    TableColumn(
        field="Change",
        formatter=formatter03,
        title="Change",
    ),
    TableColumn(
        field="Pval_95",
        formatter=formatter03,
        title="Pval_95",
    ),
]
data_table = DataTable(
    source=source5,
    columns=columns5,
    width=500,
    height=450,
    row_height=21,
    styles={
        "margin-top": "10px",
        "margin-left": "10px",
        "padding": "15px",
        "border-radius": "10px",
        "box-shadow": "0 3px 3px #fcc020",
        "background-color": "hsl(0, 13%, 95%)",
        "color": "black",
    },
    background="hsl(0, 13%, 95%)",
)
table_style = InlineStyleSheet(
    css="""
    .slick-header-columns {
        font-family: arial;
        font-weight: bold;
        font-size: 10pt;
        color: #ff0bb6;
        text-align: center;
    }
:host div[class*="slick-cell"][class*="selected"] {
    background: hsl(188, 100%, 75%) !important;
}


    

"""
)

data_table.stylesheets = [table_style]

# take some notes
text_area_input = TextAreaInput(
    value=" ", rows=10, cols=150, title="My notes:", stylesheets=[tais]
)
text_area_input.js_on_change(
    "value",
    CustomJS(
        code="""
    console.log('text_area_input: value=' + this.value, this.toString())
"""
    ),
)


# display text
div1 = Div(text="", height=15, width=1000)

div2 = Div(
    text="""
    <div style="background-color: #fff187; padding: 1px; border-radius: 3px; box-shadow: 3px 3px 12px rgba(225, 225, 225, 0.2);">
        <p style='font-family: Arial;font-size: 18px; color: hsl(0, 0%, 21%);'> Welcome to <b>⛅️🌅 EarthSense: GDB Drivers and Climate.</b> Click over a grid or select a region to explore the corresponding multi-decadal fluctuations of climatic parameters 🌍🌞</p>
    </div>
    """,
    height=30,
    width=1500,
)

div1x = Div(
    text="Correlation and Changes of Annual Anomalies. Strong ones are denoted with colours.",
    height=15,
    width=900,
    styles={"color": "#ffcd27", "margin-top": "-10px", "margin-left": "-500px"},
)

div3 = Div(
    text="""<br>
    <div style="background-color: #e5a4ff; padding: 5px; border-radius: 3px; box-shadow: 3px 3px 12px rgba(255, 230, 0, 0.8);">
        <p style='font-family: Arial;font-size: 20px; color: #37122e;'> Made with ❤️‍🔥 by Michael Stamatis</p>
        <p style='font-family: Arial;font-size: 17px; color: #37122e;'>[email removed], <a href="https://mixstam.netlify.app/" target="_blank">Homepage</a>, <a href="https://linkedin.com/in/michael-stamatis-85756116a" target="_blank"</a>Linkedin, <a href="https://github.com/mixstam1821" target="_blank"</a>Github, <a href="https://www.researchgate.net/profile/Michael-Stamatis-2" target="_blank"</a>Publications</p>

    </div>
""",
    height=360,
    width=700,
)

lisa_a3 = list(we1.data_vars)
lisa_a4 = list(impac1.data_vars)

# Create a Div to display the download link
download_link1 = Div(
    text="",
    width=100,
    height=20,
    styles={
        "border-radius": "10px",
        "background-color": "#ff8888",
        "margin-top": "15px",
        "padding-left": "3px",
    },
)
download_link2 = Div(
    text="",
    width=85,
    height=20,
    styles={
        "border-radius": "10px",
        "background-color": "#aeff88",
        "margin-top": "15px",
        "padding-left": "12px",
    },
)
download_link3 = Div(
    text="",
    width=85,
    height=20,
    styles={
        "border-radius": "10px",
        "background-color": "#8bd5ff",
        "margin-top": "15px",
        "padding-left": "11px",
    },
)


#########################
# --- The CALLBACK ---- #
#########################


# Callback function
def update_timeseries(attr, old, new):
    Xlong = longitudes[new[-1]["i"]]
    Xlati = latitudes[new[-1]["j"]]

    s2_ac1 = a1["AC1"].sel(lon=Xlong, lat=Xlati).values
    s2_ac2 = a1["AC2"].sel(lat=Xlati, lon=Xlong).values
    s2_ac3 = a1["AC3"].sel(lat=Xlati, lon=Xlong).values
    s2_tau1 = a1["TAU1"].sel(lat=Xlati, lon=Xlong).values
    s2_tau2 = a1["TAU2"].sel(lat=Xlati, lon=Xlong).values
    s2_tau3 = a1["TAU3"].sel(lat=Xlati, lon=Xlong).values
    s2_aod = a1["AOD"].sel(lat=Xlati, lon=Xlong).values
    s2_ssa = a1["SSA"].sel(lat=Xlati, lon=Xlong).values
    s2_asym = a1["ASYM"].sel(lat=Xlati, lon=Xlong).values
    s2_h2o = a1["H2O"].sel(lat=Xlati, lon=Xlong).values
    s2_o3 = a1["O3"].sel(lat=Xlati, lon=Xlong).values
    s2_slope = a1["slope"].sel(lat=Xlati, lon=Xlong).values

    s3_ac1 = we1["AC1"].sel(lat=Xlati, lon=Xlong).values.flatten()
    s3_ac2 = we1["AC2"].sel(lat=Xlati, lon=Xlong).values.flatten()
    s3_ac3 = we1["AC3"].sel(lat=Xlati, lon=Xlong).values.flatten()
    s3_tau1 = we1["TAU1"].sel(lat=Xlati, lon=Xlong).values.flatten()
    s3_tau2 = we1["TAU2"].sel(lat=Xlati, lon=Xlong).values.flatten()
    s3_tau3 = we1["TAU3"].sel(lat=Xlati, lon=Xlong).values.flatten()
    s3_aod = we1["AOD"].sel(lat=Xlati, lon=Xlong).values.flatten()
    s3_ssa = we1["SSA"].sel(lat=Xlati, lon=Xlong).values.flatten()
    s3_asym = we1["ASYM"].sel(lat=Xlati, lon=Xlong).values.flatten()
    s3_h2o = we1["H2O"].sel(lat=Xlati, lon=Xlong).values.flatten()
    s3_o3 = we1["O3"].sel(lat=Xlati, lon=Xlong).values.flatten()
    s3_ssr = we1["SSR"].sel(lat=Xlati, lon=Xlong).values.flatten()

    s3_ac1_sg = savgol_filter(s3_ac1, 10, 3)
    s3_ac1_sgN = (s3_ac1_sg - np.nanmean(s3_ac1_sg)) / np.nanstd(s3_ac1_sg)
    x = np.arange(len(s3_ac1_sg))
    spline = UnivariateSpline(x, s3_ac1_sgN, s=15)
    s3_ac1_sgN = spline(x)

    s3_ac2_sg = savgol_filter(s3_ac2, 10, 3)
    s3_ac2_sgN = (s3_ac2_sg - np.nanmean(s3_ac2_sg)) / np.nanstd(s3_ac2_sg)
    spline = UnivariateSpline(x, s3_ac2_sgN, s=15)
    s3_ac2_sgN = spline(x)

    s3_ac3_sg = savgol_filter(s3_ac3, 10, 3)
    s3_ac3_sgN = (s3_ac3_sg - np.nanmean(s3_ac3_sg)) / np.nanstd(s3_ac3_sg)
    spline = UnivariateSpline(x, s3_ac3_sgN, s=15)
    s3_ac3_sgN = spline(x)

    s3_tau1_sg = savgol_filter(s3_tau1, 10, 3)
    s3_tau1_sgN = (s3_tau1_sg - np.nanmean(s3_tau1_sg)) / np.nanstd(s3_tau1_sg)
    spline = UnivariateSpline(x, s3_tau1_sgN, s=15)
    s3_tau1_sgN = spline(x)

    s3_tau2_sg = savgol_filter(s3_tau2, 10, 3)
    s3_tau2_sgN = (s3_tau2_sg - np.nanmean(s3_tau2_sg)) / np.nanstd(s3_tau2_sg)
    spline = UnivariateSpline(x, s3_tau2_sgN, s=15)
    s3_tau2_sgN = spline(x)

    s3_tau3_sg = savgol_filter(s3_tau3, 10, 3)
    s3_tau3_sgN = (s3_tau3_sg - np.nanmean(s3_tau3_sg)) / np.nanstd(s3_tau3_sg)
    spline = UnivariateSpline(x, s3_tau3_sgN, s=15)
    s3_tau3_sgN = spline(x)

    s3_aod_sg = savgol_filter(s3_aod, 10, 3)
    s3_aod_sgN = (s3_aod_sg - np.nanmean(s3_aod_sg)) / np.nanstd(s3_aod_sg)
    spline = UnivariateSpline(x, s3_aod_sgN, s=15)
    s3_aod_sgN = spline(x)

    s3_ssa_sg = savgol_filter(s3_ssa, 10, 3)
    s3_ssa_sgN = (s3_ssa_sg - np.nanmean(s3_ssa_sg)) / np.nanstd(s3_ssa_sg)
    spline = UnivariateSpline(x, s3_ssa_sgN, s=15)
    s3_ssa_sgN = spline(x)

    s3_asym_sg = savgol_filter(s3_asym, 10, 3)
    s3_asym_sgN = (s3_asym_sg - np.nanmean(s3_asym_sg)) / np.nanstd(s3_asym_sg)
    spline = UnivariateSpline(x, s3_asym_sgN, s=15)
    s3_asym_sgN = spline(x)

    s3_h2o_sg = savgol_filter(s3_h2o, 10, 3)
    s3_h2o_sgN = (s3_h2o_sg - np.nanmean(s3_h2o_sg)) / np.nanstd(s3_h2o_sg)
    spline = UnivariateSpline(x, s3_h2o_sgN, s=15)
    s3_h2o_sgN = spline(x)

    s3_o3_sg = savgol_filter(s3_o3, 10, 3)
    s3_o3_sgN = (s3_o3_sg - np.nanmean(s3_o3_sg)) / np.nanstd(s3_o3_sg)
    spline = UnivariateSpline(x, s3_o3_sgN, s=15)
    s3_o3_sgN = spline(x)

    s3_ssr_sg = savgol_filter(s3_ssr, 10, 3)
    s3_ssr_sgN = (s3_ssr_sg - np.nanmean(s3_ssr_sg)) / np.nanstd(s3_ssr_sg)
    spline = UnivariateSpline(x, s3_ssr_sgN, s=15)
    s3_ssr_sgN = spline(x)

    s4_Temperature = impac1["Temperature"].sel(lat=Xlati, lon=Xlong).values.flatten()
    s4_Precipitation = (
        impac1["Precipitation"].sel(lat=Xlati, lon=Xlong).values.flatten()
    )
    s4_Evaporation = impac1["Evaporation"].sel(lat=Xlati, lon=Xlong).values.flatten()
    s4_Snow_Evaporation = (
        impac1["Snow_Evaporation"].sel(lat=Xlati, lon=Xlong).values.flatten()
    )
    s4_Snow_Density = impac1["Snow_Density"].sel(lat=Xlati, lon=Xlong).values.flatten()
    s4_Sea_Ice_Fraction = (
        impac1["Sea_Ice_Fraction"].sel(lat=Xlati, lon=Xlong).values.flatten()
    )
    s4_SSR = impac1["SSR"].sel(lat=Xlati, lon=Xlong).values.flatten()

    s4_Temperature_sg = savgol_filter(s4_Temperature, 10, 3)
    s4_Temperature_sgN = (
        s4_Temperature_sg - np.nanmean(s4_Temperature_sg)
    ) / np.nanstd(s4_Temperature_sg)
    x = np.arange(len(s4_Temperature_sgN))
    spline = UnivariateSpline(x, s4_Temperature_sgN, s=15)
    s4_Temperature_sgN = spline(x)

    s4_Precipitation_sg = savgol_filter(s4_Precipitation, 10, 3)
    s4_Precipitation_sgN = (
        s4_Precipitation_sg - np.nanmean(s4_Precipitation_sg)
    ) / np.nanstd(s4_Precipitation_sg)
    spline = UnivariateSpline(x, s4_Precipitation_sgN, s=15)
    s4_Precipitation_sgN = spline(x)

    s4_Evaporation_sg = savgol_filter(s4_Evaporation, 10, 3)
    s4_Evaporation_sgN = (
        s4_Evaporation_sg - np.nanmean(s4_Evaporation_sg)
    ) / np.nanstd(s4_Evaporation_sg)
    spline = UnivariateSpline(x, s4_Evaporation_sgN, s=15)
    s4_Evaporation_sgN = spline(x)

    s4_Snow_Evaporation_sg = savgol_filter(s4_Snow_Evaporation, 10, 3)
    s4_Snow_Evaporation_sgN = (
        s4_Snow_Evaporation_sg - np.nanmean(s4_Snow_Evaporation_sg)
    ) / np.nanstd(s4_Snow_Evaporation_sg)
    spline = UnivariateSpline(x, s4_Snow_Evaporation_sgN, s=15)
    s4_Snow_Evaporation_sgN = spline(x)

    s4_Snow_Density_sg = savgol_filter(s4_Snow_Density, 10, 3)
    s4_Snow_Density_sgN = (
        s4_Snow_Density_sg - np.nanmean(s4_Snow_Density_sg)
    ) / np.nanstd(s4_Snow_Density_sg)
    spline = UnivariateSpline(x, s4_Snow_Density_sgN, s=15)
    s4_Snow_Density_sgN = spline(x)

    s4_Sea_Ice_Fraction_sg = savgol_filter(s4_Sea_Ice_Fraction, 10, 3)
    s4_Sea_Ice_Fraction_sgN = (
        s4_Sea_Ice_Fraction_sg - np.nanmean(s4_Sea_Ice_Fraction_sg)
    ) / np.nanstd(s4_Sea_Ice_Fraction_sg)
    spline = UnivariateSpline(x, s4_Sea_Ice_Fraction_sgN, s=15)
    s4_Sea_Ice_Fraction_sgN = spline(x)

    s4_SSR_sg = savgol_filter(s4_SSR, 10, 3)
    s4_SSR_sgN = (s4_SSR_sg - np.nanmean(s4_SSR_sg)) / np.nanstd(s4_SSR_sg)
    spline = UnivariateSpline(x, s4_SSR_sgN, s=15)
    s4_SSR_sgN = spline(x)

    s2.data = dict(
        x=variables,
        y=[
            s2_ac1,
            s2_ac2,
            s2_ac3,
            s2_tau1,
            s2_tau2,
            s2_tau3,
            s2_aod,
            s2_ssa,
            s2_asym,
            s2_h2o,
            s2_o3,
            s2_slope,
        ],
        colors=colorss,
        hatch_pattern=[""] * 11 + ["@"],
    )

    # s3.data = dict(x=xdates, AC1=s3_ac1, AC2=s3_ac2, AC3=s3_ac3, TAU1=s3_tau1, TAU2=s3_tau2, TAU3=s3_tau3, AOD=s3_aod, SSA=s3_ssa,ASYM=s3_asym,H2O=s3_h2o,O3=s3_o3, SSR = s3_ssr)
    s3.data = dict(
        x=xdates,
        AC1=s3_ac1_sgN,
        AC2=s3_ac2_sgN,
        AC3=s3_ac3_sgN,
        COT1=s3_tau1_sgN,
        COT2=s3_tau2_sgN,
        COT3=s3_tau3_sgN,
        AOD=s3_aod_sgN,
        SSA=s3_ssa_sgN,
        ASYM=s3_asym_sgN,
        H2O=s3_h2o_sgN,
        O3=s3_o3_sgN,
        SSR=s3_ssr_sgN,
        AC1x=s3_ac1,
        AC2x=s3_ac2,
        AC3x=s3_ac3,
        COT1x=s3_tau1,
        COT2x=s3_tau2,
        COT3x=s3_tau3,
        AODx=s3_aod,
        SSAx=s3_ssa,
        ASYMx=s3_asym,
        H2Ox=s3_h2o,
        O3x=s3_o3,
        SSRx=s3_ssr,
    )
    # s4.data = dict(x=xdates, Temperature = s4_Temperature, Precipitation = s4_Precipitation, Evaporation = s4_Evaporation, Snow_Evaporation = s4_Snow_Evaporation, Snow_Density = s4_Snow_Density, Sea_Ice_Fraction = s4_Sea_Ice_Fraction, SSR = s4_SSR)
    s4.data = dict(
        x=xdates,
        Temperaturex=s4_Temperature,
        Precipitationx=s4_Precipitation,
        Evaporationx=s4_Evaporation,
        Snow_Evaporationx=s4_Snow_Evaporation,
        Snow_Densityx=s4_Snow_Density,
        Sea_Ice_Fractionx=s4_Sea_Ice_Fraction,
        SSRx=s4_SSR,
        Temperature=s4_Temperature_sgN,
        Precipitation=s4_Precipitation_sgN,
        Evaporation=s4_Evaporation_sgN,
        Snow_Evaporation=s4_Snow_Evaporation_sgN,
        Snow_Density=s4_Snow_Density_sgN,
        Sea_Ice_Fraction=s4_Sea_Ice_Fraction_sgN,
        SSR=s4_SSR_sgN,
    )
    # Convert the data to a CSV string

    lengg = np.arange(35)
    source5.data = dict(
        Parameters=[
            "AC1",
            "AC2",
            "AC3",
            "COT1",
            "COT2",
            "COT3",
            "AOD",
            "SSA",
            "ASYM",
            "H2O",
            "O3",
            "SSR",
            "Temp",
            "Prec",
            "Evap",
            "SnowEva",
            "SnowDen",
            "SeaIce",
        ],
        Pearson_R=[
            str(np.round(sp.stats.pearsonr(s3_ac1, s3_ssr)[0], 1)),
            str(np.round(sp.stats.pearsonr(s3_ac2, s3_ssr)[0], 1)),
            str(np.round(sp.stats.pearsonr(s3_ac3, s3_ssr)[0], 1)),
            str(np.round(sp.stats.pearsonr(s3_tau1, s3_ssr)[0], 1)),
            str(np.round(sp.stats.pearsonr(s3_tau2, s3_ssr)[0], 1)),
            str(np.round(sp.stats.pearsonr(s3_tau3, s3_ssr)[0], 1)),
            str(np.round(sp.stats.pearsonr(s3_aod, s3_ssr)[0], 1)),
            str(np.round(sp.stats.pearsonr(s3_ssa, s3_ssr)[0], 1)),
            str(np.round(sp.stats.pearsonr(s3_asym, s3_ssr)[0], 1)),
            str(np.round(sp.stats.pearsonr(s3_h2o, s3_ssr)[0], 1)),
            str(np.round(sp.stats.pearsonr(s3_o3, s3_ssr)[0], 1)),
            str(np.round(sp.stats.pearsonr(s3_ssr, s3_ssr)[0], 1)),
            str(np.round(sp.stats.pearsonr(s4_Temperature, s4_SSR)[0], 1)),
            str(np.round(sp.stats.pearsonr(s4_Precipitation, s4_SSR)[0], 1)),
            str(np.round(sp.stats.pearsonr(s4_Evaporation, s4_SSR)[0], 1)),
            str(np.round(sp.stats.pearsonr(s4_Snow_Evaporation, s4_SSR)[0], 1)),
            str(np.round(sp.stats.pearsonr(s4_Snow_Density, s4_SSR)[0], 1)),
            str(np.round(sp.stats.pearsonr(s4_Sea_Ice_Fraction, s4_SSR)[0], 1)),
        ],
        Spearman_R=[
            np.round(sp.stats.spearmanr(s3_ac1, s3_ssr)[0], 1),
            np.round(sp.stats.spearmanr(s3_ac2, s3_ssr)[0], 1),
            np.round(sp.stats.spearmanr(s3_ac3, s3_ssr)[0], 1),
            np.round(sp.stats.spearmanr(s3_tau1, s3_ssr)[0], 1),
            np.round(sp.stats.spearmanr(s3_tau2, s3_ssr)[0], 1),
            np.round(sp.stats.spearmanr(s3_tau3, s3_ssr)[0], 1),
            np.round(sp.stats.spearmanr(s3_aod, s3_ssr)[0], 1),
            np.round(sp.stats.spearmanr(s3_ssa, s3_ssr)[0], 1),
            np.round(sp.stats.spearmanr(s3_asym, s3_ssr)[0], 1),
            np.round(sp.stats.spearmanr(s3_h2o, s3_ssr)[0], 1),
            np.round(sp.stats.spearmanr(s3_o3, s3_ssr)[0], 1),
            np.round(sp.stats.spearmanr(s3_ssr, s3_ssr)[0], 1),
            np.round(sp.stats.spearmanr(s4_Temperature, s4_SSR)[0], 1),
            np.round(sp.stats.spearmanr(s4_Precipitation, s4_SSR)[0], 1),
            np.round(sp.stats.spearmanr(s4_Evaporation, s4_SSR)[0], 1),
            np.round(sp.stats.spearmanr(s4_Snow_Evaporation, s4_SSR)[0], 1),
            np.round(sp.stats.spearmanr(s4_Snow_Density, s4_SSR)[0], 1),
            np.round(sp.stats.spearmanr(s4_Sea_Ice_Fraction, s4_SSR)[0], 1),
        ],
        Change=[
            np.round(sp.stats.theilslopes(s3_ac1)[0] * 35, 4),
            np.round(sp.stats.theilslopes(s3_ac2)[0] * 35, 4),
            np.round(sp.stats.theilslopes(s3_ac3)[0] * 35, 4),
            np.round(sp.stats.theilslopes(s3_tau1)[0] * 35, 4),
            np.round(sp.stats.theilslopes(s3_tau2)[0] * 35, 4),
            np.round(sp.stats.theilslopes(s3_tau3)[0] * 35, 4),
            np.round(sp.stats.theilslopes(s3_aod)[0] * 35, 4),
            np.round(sp.stats.theilslopes(s3_ssa)[0] * 35, 4),
            np.round(sp.stats.theilslopes(s3_asym)[0] * 35, 4),
            np.round(sp.stats.theilslopes(s3_h2o)[0] * 35, 4),
            np.round(sp.stats.theilslopes(s3_o3)[0] * 35, 4),
            np.round(sp.stats.theilslopes(s3_ssr)[0] * 35, 4),
            np.round(sp.stats.theilslopes(s4_Temperature)[0] * 35, 4),
            np.round(sp.stats.theilslopes(s4_Precipitation)[0] * 35, 7),
            np.round(sp.stats.theilslopes(s4_Evaporation)[0] * 35, 7),
            np.round(sp.stats.theilslopes(s4_Snow_Evaporation)[0] * 35, 7),
            np.round(sp.stats.theilslopes(s4_Snow_Density)[0] * 35, 4),
            np.round(sp.stats.theilslopes(s4_Sea_Ice_Fraction)[0] * 35, 4),
        ],
        Pval_95=[
            np.round(sp.stats.linregress(lengg, s3_ac1).pvalue, 3),
            np.round(sp.stats.linregress(lengg, s3_ac2).pvalue, 3),
            np.round(sp.stats.linregress(lengg, s3_ac3).pvalue, 3),
            np.round(sp.stats.linregress(lengg, s3_tau1).pvalue, 3),
            np.round(sp.stats.linregress(lengg, s3_tau2).pvalue, 3),
            np.round(sp.stats.linregress(lengg, s3_tau3).pvalue, 3),
            np.round(sp.stats.linregress(lengg, s3_aod).pvalue, 3),
            np.round(sp.stats.linregress(lengg, s3_ssa).pvalue, 3),
            np.round(sp.stats.linregress(lengg, s3_asym).pvalue, 3),
            np.round(sp.stats.linregress(lengg, s3_h2o).pvalue, 3),
            np.round(sp.stats.linregress(lengg, s3_o3).pvalue, 3),
            np.round(sp.stats.linregress(lengg, s3_ssr).pvalue, 3),
            np.round(sp.stats.linregress(lengg, s4_Temperature).pvalue, 3),
            np.round(sp.stats.linregress(lengg, s4_Precipitation).pvalue, 3),
            np.round(sp.stats.linregress(lengg, s4_Evaporation).pvalue, 3),
            np.round(sp.stats.linregress(lengg, s4_Snow_Evaporation).pvalue, 3),
            np.round(sp.stats.linregress(lengg, s4_Snow_Density).pvalue, 3),
            np.round(sp.stats.linregress(lengg, s4_Sea_Ice_Fraction).pvalue, 3),
        ],
    )

    df1 = pd.DataFrame(s2.data)
    csv_string1 = df1.to_csv(index=False)

    # Encode the CSV string as a base64 data URL
    b641 = base64.b64encode(csv_string1.encode()).decode()
    href1 = f'<a href="data:text/csv;base64,{b641}" download="contributions_lon{Xlong}_lat{Xlati}.csv">Get Contributions</a>'

    # Update the Div to display the download link
    download_link1.text = href1

    # Convert the data to a CSV string
    df2 = pd.DataFrame(s3.data)
    csv_string2 = df2.to_csv(index=False)

    # Encode the CSV string as a base64 data URL
    b642 = base64.b64encode(csv_string2.encode()).decode()
    href2 = f'<a href="data:text/csv;base64,{b642}" download="GDB_Drivers_timeserie_lon{Xlong}_lat{Xlati}.csv">Get Drivers</a>'

    # Update the Div to display the download link
    download_link2.text = href2

    # Convert the data to a CSV string
    df3 = pd.DataFrame(s4.data)
    csv_string3 = df3.to_csv(index=False)

    # Encode the CSV string as a base64 data URL
    b643 = base64.b64encode(csv_string3.encode()).decode()
    href3 = f'<a href="data:text/csv;base64,{b643}" download="Climate_timeseries_lon{Xlong}_lat{Xlati}.csv">Get Climate</a>'

    # Update the Div to display the download link
    download_link3.text = href3

    del new

    div1.text = f"""
    <div style="padding: 1px;margin-top:0">
        <p style='font-family:Arial;font-size: 18px;  color: #06d8d8;'>
Current position: <b>lon</b>: {Xlong}<sup>o</sup>, <b>lat</b>: {Xlati}<sup>o</sup>, <b>GDB</b>: {gdbdc.sel(lat=Xlati, lon=Xlong).values.tolist():.2f} Wm<sup>-2</sup>decade<sup>-1</sup> </p>
    </div>
                """


# this is for selection
def getBoxDims(event):  

    if event.__dict__["geometry"]["type"] == "rect":
        mie = event.__dict__["geometry"]
        xl = mie["x0"]
        xr = mie["x1"]
        yl = mie["y0"]
        yu = mie["y1"]

        Xlong1 = xl
        Xlong2 = xr

        Xlati1 = yl
        Xlati2 = yu

        wwq = a1["AC1"].sel(lon=slice(Xlong1, Xlong2), lat=slice(Xlati1, Xlati2)).lat
        s2_ac1 = (
            a1["AC1"]
            .sel(lon=slice(Xlong1, Xlong2), lat=slice(Xlati1, Xlati2))
            .weighted(np.cos(np.deg2rad(wwq)))
            .mean(("lat", "lon"))
            .values
        )
        s2_ac2 = (
            a1["AC2"]
            .sel(lat=slice(Xlati1, Xlati2), lon=slice(Xlong1, Xlong2))
            .weighted(np.cos(np.deg2rad(wwq)))
            .mean(("lat", "lon"))
            .values
        )
        s2_ac3 = (
            a1["AC3"]
            .sel(lat=slice(Xlati1, Xlati2), lon=slice(Xlong1, Xlong2))
            .weighted(np.cos(np.deg2rad(wwq)))
            .mean(("lat", "lon"))
            .values
        )
        s2_tau1 = (
            a1["TAU1"]
            .sel(lat=slice(Xlati1, Xlati2), lon=slice(Xlong1, Xlong2))
            .weighted(np.cos(np.deg2rad(wwq)))
            .mean(("lat", "lon"))
            .values
        )
        s2_tau2 = (
            a1["TAU2"]
            .sel(lat=slice(Xlati1, Xlati2), lon=slice(Xlong1, Xlong2))
            .weighted(np.cos(np.deg2rad(wwq)))
            .mean(("lat", "lon"))
            .values
        )
        s2_tau3 = (
            a1["TAU3"]
            .sel(lat=slice(Xlati1, Xlati2), lon=slice(Xlong1, Xlong2))
            .weighted(np.cos(np.deg2rad(wwq)))
            .mean(("lat", "lon"))
            .values
        )
        s2_aod = (
            a1["AOD"]
            .sel(lat=slice(Xlati1, Xlati2), lon=slice(Xlong1, Xlong2))
            .weighted(np.cos(np.deg2rad(wwq)))
            .mean(("lat", "lon"))
            .values
        )
        s2_ssa = (
            a1["SSA"]
            .sel(lat=slice(Xlati1, Xlati2), lon=slice(Xlong1, Xlong2))
            .weighted(np.cos(np.deg2rad(wwq)))
            .mean(("lat", "lon"))
            .values
        )
        s2_asym = (
            a1["ASYM"]
            .sel(lat=slice(Xlati1, Xlati2), lon=slice(Xlong1, Xlong2))
            .weighted(np.cos(np.deg2rad(wwq)))
            .mean(("lat", "lon"))
            .values
        )
        s2_h2o = (
            a1["H2O"]
            .sel(lat=slice(Xlati1, Xlati2), lon=slice(Xlong1, Xlong2))
            .weighted(np.cos(np.deg2rad(wwq)))
            .mean(("lat", "lon"))
            .values
        )
        s2_o3 = (
            a1["O3"]
            .sel(lat=slice(Xlati1, Xlati2), lon=slice(Xlong1, Xlong2))
            .weighted(np.cos(np.deg2rad(wwq)))
            .mean(("lat", "lon"))
            .values
        )
        s2_slope = (
            a1["slope"]
            .sel(lat=slice(Xlati1, Xlati2), lon=slice(Xlong1, Xlong2))
            .weighted(np.cos(np.deg2rad(wwq)))
            .mean(("lat", "lon"))
            .values
        )

        s3_ac1 = (
            we1["AC1"]
            .sel(lat=slice(Xlati1, Xlati2), lon=slice(Xlong1, Xlong2))
            .weighted(np.cos(np.deg2rad(wwq)))
            .mean(("lat", "lon"))
            .values.flatten()
        )
        s3_ac2 = (
            we1["AC2"]
            .sel(lat=slice(Xlati1, Xlati2), lon=slice(Xlong1, Xlong2))
            .weighted(np.cos(np.deg2rad(wwq)))
            .mean(("lat", "lon"))
            .values.flatten()
        )
        s3_ac3 = (
            we1["AC3"]
            .sel(lat=slice(Xlati1, Xlati2), lon=slice(Xlong1, Xlong2))
            .weighted(np.cos(np.deg2rad(wwq)))
            .mean(("lat", "lon"))
            .values.flatten()
        )
        s3_tau1 = (
            we1["TAU1"]
            .sel(lat=slice(Xlati1, Xlati2), lon=slice(Xlong1, Xlong2))
            .weighted(np.cos(np.deg2rad(wwq)))
            .mean(("lat", "lon"))
            .values.flatten()
        )
        s3_tau2 = (
            we1["TAU2"]
            .sel(lat=slice(Xlati1, Xlati2), lon=slice(Xlong1, Xlong2))
            .weighted(np.cos(np.deg2rad(wwq)))
            .mean(("lat", "lon"))
            .values.flatten()
        )
        s3_tau3 = (
            we1["TAU3"]
            .sel(lat=slice(Xlati1, Xlati2), lon=slice(Xlong1, Xlong2))
            .weighted(np.cos(np.deg2rad(wwq)))
            .mean(("lat", "lon"))
            .values.flatten()
        )
        s3_aod = (
            we1["AOD"]
            .sel(lat=slice(Xlati1, Xlati2), lon=slice(Xlong1, Xlong2))
            .weighted(np.cos(np.deg2rad(wwq)))
            .mean(("lat", "lon"))
            .values.flatten()
        )
        s3_ssa = (
            we1["SSA"]
            .sel(lat=slice(Xlati1, Xlati2), lon=slice(Xlong1, Xlong2))
            .weighted(np.cos(np.deg2rad(wwq)))
            .mean(("lat", "lon"))
            .values.flatten()
        )
        s3_asym = (
            we1["ASYM"]
            .sel(lat=slice(Xlati1, Xlati2), lon=slice(Xlong1, Xlong2))
            .weighted(np.cos(np.deg2rad(wwq)))
            .mean(("lat", "lon"))
            .values.flatten()
        )
        s3_h2o = (
            we1["H2O"]
            .sel(lat=slice(Xlati1, Xlati2), lon=slice(Xlong1, Xlong2))
            .weighted(np.cos(np.deg2rad(wwq)))
            .mean(("lat", "lon"))
            .values.flatten()
        )
        s3_o3 = (
            we1["O3"]
            .sel(lat=slice(Xlati1, Xlati2), lon=slice(Xlong1, Xlong2))
            .weighted(np.cos(np.deg2rad(wwq)))
            .mean(("lat", "lon"))
            .values.flatten()
        )
        s3_ssr = (
            we1["SSR"]
            .sel(lat=slice(Xlati1, Xlati2), lon=slice(Xlong1, Xlong2))
            .weighted(np.cos(np.deg2rad(wwq)))
            .mean(("lat", "lon"))
            .values.flatten()
        )

        s3_ac1_sg = savgol_filter(s3_ac1, 10, 3)
        s3_ac1_sgN = (s3_ac1_sg - np.nanmean(s3_ac1_sg)) / np.nanstd(s3_ac1_sg)
        x = np.arange(len(s3_ac1_sg))
        spline = UnivariateSpline(x, s3_ac1_sgN, s=15)
        s3_ac1_sgN = spline(x)

        s3_ac2_sg = savgol_filter(s3_ac2, 10, 3)
        s3_ac2_sgN = (s3_ac2_sg - np.nanmean(s3_ac2_sg)) / np.nanstd(s3_ac2_sg)
        spline = UnivariateSpline(x, s3_ac2_sgN, s=15)
        s3_ac2_sgN = spline(x)

        s3_ac3_sg = savgol_filter(s3_ac3, 10, 3)
        s3_ac3_sgN = (s3_ac3_sg - np.nanmean(s3_ac3_sg)) / np.nanstd(s3_ac3_sg)
        spline = UnivariateSpline(x, s3_ac3_sgN, s=15)
        s3_ac3_sgN = spline(x)

        s3_tau1_sg = savgol_filter(s3_tau1, 10, 3)
        s3_tau1_sgN = (s3_tau1_sg - np.nanmean(s3_tau1_sg)) / np.nanstd(s3_tau1_sg)
        spline = UnivariateSpline(x, s3_tau1_sgN, s=15)
        s3_tau1_sgN = spline(x)

        s3_tau2_sg = savgol_filter(s3_tau2, 10, 3)
        s3_tau2_sgN = (s3_tau2_sg - np.nanmean(s3_tau2_sg)) / np.nanstd(s3_tau2_sg)
        spline = UnivariateSpline(x, s3_tau2_sgN, s=15)
        s3_tau2_sgN = spline(x)

        s3_tau3_sg = savgol_filter(s3_tau3, 10, 3)
        s3_tau3_sgN = (s3_tau3_sg - np.nanmean(s3_tau3_sg)) / np.nanstd(s3_tau3_sg)
        spline = UnivariateSpline(x, s3_tau3_sgN, s=15)
        s3_tau3_sgN = spline(x)

        s3_aod_sg = savgol_filter(s3_aod, 10, 3)
        s3_aod_sgN = (s3_aod_sg - np.nanmean(s3_aod_sg)) / np.nanstd(s3_aod_sg)
        spline = UnivariateSpline(x, s3_aod_sgN, s=15)
        s3_aod_sgN = spline(x)

        s3_ssa_sg = savgol_filter(s3_ssa, 10, 3)
        s3_ssa_sgN = (s3_ssa_sg - np.nanmean(s3_ssa_sg)) / np.nanstd(s3_ssa_sg)
        spline = UnivariateSpline(x, s3_ssa_sgN, s=15)
        s3_ssa_sgN = spline(x)

        s3_asym_sg = savgol_filter(s3_asym, 10, 3)
        s3_asym_sgN = (s3_asym_sg - np.nanmean(s3_asym_sg)) / np.nanstd(s3_asym_sg)
        spline = UnivariateSpline(x, s3_asym_sgN, s=15)
        s3_asym_sgN = spline(x)

        s3_h2o_sg = savgol_filter(s3_h2o, 10, 3)
        s3_h2o_sgN = (s3_h2o_sg - np.nanmean(s3_h2o_sg)) / np.nanstd(s3_h2o_sg)
        spline = UnivariateSpline(x, s3_h2o_sgN, s=15)
        s3_h2o_sgN = spline(x)

        s3_o3_sg = savgol_filter(s3_o3, 10, 3)
        s3_o3_sgN = (s3_o3_sg - np.nanmean(s3_o3_sg)) / np.nanstd(s3_o3_sg)
        spline = UnivariateSpline(x, s3_o3_sgN, s=15)
        s3_o3_sgN = spline(x)

        s3_ssr_sg = savgol_filter(s3_ssr, 10, 3)
        s3_ssr_sgN = (s3_ssr_sg - np.nanmean(s3_ssr_sg)) / np.nanstd(s3_ssr_sg)
        spline = UnivariateSpline(x, s3_ssr_sgN, s=15)
        s3_ssr_sgN = spline(x)

        s4_Temperature = (
            impac1["Temperature"]
            .sel(lat=slice(Xlati1, Xlati2), lon=slice(Xlong1, Xlong2))
            .weighted(np.cos(np.deg2rad(wwq)))
            .mean(("lat", "lon"))
            .values.flatten()
        )
        s4_Precipitation = (
            impac1["Precipitation"]
            .sel(lat=slice(Xlati1, Xlati2), lon=slice(Xlong1, Xlong2))
            .weighted(np.cos(np.deg2rad(wwq)))
            .mean(("lat", "lon"))
            .values.flatten()
        )
        s4_Evaporation = (
            impac1["Evaporation"]
            .sel(lat=slice(Xlati1, Xlati2), lon=slice(Xlong1, Xlong2))
            .weighted(np.cos(np.deg2rad(wwq)))
            .mean(("lat", "lon"))
            .values.flatten()
        )
        s4_Snow_Evaporation = (
            impac1["Snow_Evaporation"]
            .sel(lat=slice(Xlati1, Xlati2), lon=slice(Xlong1, Xlong2))
            .weighted(np.cos(np.deg2rad(wwq)))
            .mean(("lat", "lon"))
            .values.flatten()
        )
        s4_Snow_Density = (
            impac1["Snow_Density"]
            .sel(lat=slice(Xlati1, Xlati2), lon=slice(Xlong1, Xlong2))
            .weighted(np.cos(np.deg2rad(wwq)))
            .mean(("lat", "lon"))
            .values.flatten()
        )
        s4_Sea_Ice_Fraction = (
            impac1["Sea_Ice_Fraction"]
            .sel(lat=slice(Xlati1, Xlati2), lon=slice(Xlong1, Xlong2))
            .weighted(np.cos(np.deg2rad(wwq)))
            .mean(("lat", "lon"))
            .values.flatten()
        )
        s4_SSR = (
            impac1["SSR"]
            .sel(lat=slice(Xlati1, Xlati2), lon=slice(Xlong1, Xlong2))
            .weighted(np.cos(np.deg2rad(wwq)))
            .mean(("lat", "lon"))
            .values.flatten()
        )

        s4_Temperature_sg = savgol_filter(s4_Temperature, 10, 3)
        s4_Temperature_sgN = (
            s4_Temperature_sg - np.nanmean(s4_Temperature_sg)
        ) / np.nanstd(s4_Temperature_sg)
        x = np.arange(len(s4_Temperature_sgN))
        spline = UnivariateSpline(x, s4_Temperature_sgN, s=15)
        s4_Temperature_sgN = spline(x)

        s4_Precipitation_sg = savgol_filter(s4_Precipitation, 10, 3)
        s4_Precipitation_sgN = (
            s4_Precipitation_sg - np.nanmean(s4_Precipitation_sg)
        ) / np.nanstd(s4_Precipitation_sg)
        spline = UnivariateSpline(x, s4_Precipitation_sgN, s=15)
        s4_Precipitation_sgN = spline(x)

        s4_Evaporation_sg = savgol_filter(s4_Evaporation, 10, 3)
        s4_Evaporation_sgN = (
            s4_Evaporation_sg - np.nanmean(s4_Evaporation_sg)
        ) / np.nanstd(s4_Evaporation_sg)
        spline = UnivariateSpline(x, s4_Evaporation_sgN, s=15)
        s4_Evaporation_sgN = spline(x)

        s4_Snow_Evaporation_sg = savgol_filter(s4_Snow_Evaporation, 10, 3)
        s4_Snow_Evaporation_sgN = (
            s4_Snow_Evaporation_sg - np.nanmean(s4_Snow_Evaporation_sg)
        ) / np.nanstd(s4_Snow_Evaporation_sg)
        spline = UnivariateSpline(x, s4_Snow_Evaporation_sgN, s=15)
        s4_Snow_Evaporation_sgN = spline(x)

        s4_Snow_Density_sg = savgol_filter(s4_Snow_Density, 10, 3)
        s4_Snow_Density_sgN = (
            s4_Snow_Density_sg - np.nanmean(s4_Snow_Density_sg)
        ) / np.nanstd(s4_Snow_Density_sg)
        spline = UnivariateSpline(x, s4_Snow_Density_sgN, s=15)
        s4_Snow_Density_sgN = spline(x)

        s4_Sea_Ice_Fraction_sg = savgol_filter(s4_Sea_Ice_Fraction, 10, 3)
        s4_Sea_Ice_Fraction_sgN = (
            s4_Sea_Ice_Fraction_sg - np.nanmean(s4_Sea_Ice_Fraction_sg)
        ) / np.nanstd(s4_Sea_Ice_Fraction_sg)
        spline = UnivariateSpline(x, s4_Sea_Ice_Fraction_sgN, s=15)
        s4_Sea_Ice_Fraction_sgN = spline(x)

        s4_SSR_sg = savgol_filter(s4_SSR, 10, 3)
        s4_SSR_sgN = (s4_SSR_sg - np.nanmean(s4_SSR_sg)) / np.nanstd(s4_SSR_sg)
        spline = UnivariateSpline(x, s4_SSR_sgN, s=15)
        s4_SSR_sgN = spline(x)

        s2.data = dict(
            x=variables,
            y=[
                s2_ac1,
                s2_ac2,
                s2_ac3,
                s2_tau1,
                s2_tau2,
                s2_tau3,
                s2_aod,
                s2_ssa,
                s2_asym,
                s2_h2o,
                s2_o3,
                s2_slope,
            ],
            colors=colorss,
            hatch_pattern=[""] * 11 + ["@"],
        )

        # s3.data = dict(x=xdates, AC1=s3_ac1, AC2=s3_ac2, AC3=s3_ac3, TAU1=s3_tau1, TAU2=s3_tau2, TAU3=s3_tau3, AOD=s3_aod, SSA=s3_ssa,ASYM=s3_asym,H2O=s3_h2o,O3=s3_o3, SSR = s3_ssr)
        s3.data = dict(
            x=xdates,
            AC1=s3_ac1_sgN,
            AC2=s3_ac2_sgN,
            AC3=s3_ac3_sgN,
            COT1=s3_tau1_sgN,
            COT2=s3_tau2_sgN,
            COT3=s3_tau3_sgN,
            AOD=s3_aod_sgN,
            SSA=s3_ssa_sgN,
            ASYM=s3_asym_sgN,
            H2O=s3_h2o_sgN,
            O3=s3_o3_sgN,
            SSR=s3_ssr_sgN,
            AC1x=s3_ac1,
            AC2x=s3_ac2,
            AC3x=s3_ac3,
            COT1x=s3_tau1,
            COT2x=s3_tau2,
            COT3x=s3_tau3,
            AODx=s3_aod,
            SSAx=s3_ssa,
            ASYMx=s3_asym,
            H2Ox=s3_h2o,
            O3x=s3_o3,
            SSRx=s3_ssr,
        )
        # s4.data = dict(x=xdates, Temperature = s4_Temperature, Precipitation = s4_Precipitation, Evaporation = s4_Evaporation, Snow_Evaporation = s4_Snow_Evaporation, Snow_Density = s4_Snow_Density, Sea_Ice_Fraction = s4_Sea_Ice_Fraction, SSR = s4_SSR)
        s4.data = dict(
            x=xdates,
            Temperaturex=s4_Temperature,
            Precipitationx=s4_Precipitation,
            Evaporationx=s4_Evaporation,
            Snow_Evaporationx=s4_Snow_Evaporation,
            Snow_Densityx=s4_Snow_Density,
            Sea_Ice_Fractionx=s4_Sea_Ice_Fraction,
            SSRx=s4_SSR,
            Temperature=s4_Temperature_sgN,
            Precipitation=s4_Precipitation_sgN,
            Evaporation=s4_Evaporation_sgN,
            Snow_Evaporation=s4_Snow_Evaporation_sgN,
            Snow_Density=s4_Snow_Density_sgN,
            Sea_Ice_Fraction=s4_Sea_Ice_Fraction_sgN,
            SSR=s4_SSR_sgN,
        )

        lengg = np.arange(35)
        source5.data = dict(
            Parameters=[
                "AC1",
                "AC2",
                "AC3",
                "COT1",
                "COT2",
                "COT3",
                "AOD",
                "SSA",
                "ASYM",
                "H2O",
                "O3",
                "SSR",
                "Temp",
                "Prec",
                "Evap",
                "SnowEva",
                "SnowDen",
                "SeaIce",
            ],
            Pearson_R=[
                str(np.round(sp.stats.pearsonr(s3_ac1, s3_ssr)[0], 1)),
                str(np.round(sp.stats.pearsonr(s3_ac2, s3_ssr)[0], 1)),
                str(np.round(sp.stats.pearsonr(s3_ac3, s3_ssr)[0], 1)),
                str(np.round(sp.stats.pearsonr(s3_tau1, s3_ssr)[0], 1)),
                str(np.round(sp.stats.pearsonr(s3_tau2, s3_ssr)[0], 1)),
                str(np.round(sp.stats.pearsonr(s3_tau3, s3_ssr)[0], 1)),
                str(np.round(sp.stats.pearsonr(s3_aod, s3_ssr)[0], 1)),
                str(np.round(sp.stats.pearsonr(s3_ssa, s3_ssr)[0], 1)),
                str(np.round(sp.stats.pearsonr(s3_asym, s3_ssr)[0], 1)),
                str(np.round(sp.stats.pearsonr(s3_h2o, s3_ssr)[0], 1)),
                str(np.round(sp.stats.pearsonr(s3_o3, s3_ssr)[0], 1)),
                str(np.round(sp.stats.pearsonr(s3_ssr, s3_ssr)[0], 1)),
                str(np.round(sp.stats.pearsonr(s4_Temperature, s4_SSR)[0], 1)),
                str(np.round(sp.stats.pearsonr(s4_Precipitation, s4_SSR)[0], 1)),
                str(np.round(sp.stats.pearsonr(s4_Evaporation, s4_SSR)[0], 1)),
                str(np.round(sp.stats.pearsonr(s4_Snow_Evaporation, s4_SSR)[0], 1)),
                str(np.round(sp.stats.pearsonr(s4_Snow_Density, s4_SSR)[0], 1)),
                str(np.round(sp.stats.pearsonr(s4_Sea_Ice_Fraction, s4_SSR)[0], 1)),
            ],
            Spearman_R=[
                np.round(sp.stats.spearmanr(s3_ac1, s3_ssr)[0], 1),
                np.round(sp.stats.spearmanr(s3_ac2, s3_ssr)[0], 1),
                np.round(sp.stats.spearmanr(s3_ac3, s3_ssr)[0], 1),
                np.round(sp.stats.spearmanr(s3_tau1, s3_ssr)[0], 1),
                np.round(sp.stats.spearmanr(s3_tau2, s3_ssr)[0], 1),
                np.round(sp.stats.spearmanr(s3_tau3, s3_ssr)[0], 1),
                np.round(sp.stats.spearmanr(s3_aod, s3_ssr)[0], 1),
                np.round(sp.stats.spearmanr(s3_ssa, s3_ssr)[0], 1),
                np.round(sp.stats.spearmanr(s3_asym, s3_ssr)[0], 1),
                np.round(sp.stats.spearmanr(s3_h2o, s3_ssr)[0], 1),
                np.round(sp.stats.spearmanr(s3_o3, s3_ssr)[0], 1),
                np.round(sp.stats.spearmanr(s3_ssr, s3_ssr)[0], 1),
                np.round(sp.stats.spearmanr(s4_Temperature, s4_SSR)[0], 1),
                np.round(sp.stats.spearmanr(s4_Precipitation, s4_SSR)[0], 1),
                np.round(sp.stats.spearmanr(s4_Evaporation, s4_SSR)[0], 1),
                np.round(sp.stats.spearmanr(s4_Snow_Evaporation, s4_SSR)[0], 1),
                np.round(sp.stats.spearmanr(s4_Snow_Density, s4_SSR)[0], 1),
                np.round(sp.stats.spearmanr(s4_Sea_Ice_Fraction, s4_SSR)[0], 1),
            ],
            Change=[
                np.round(sp.stats.theilslopes(s3_ac1)[0] * 35, 4),
                np.round(sp.stats.theilslopes(s3_ac2)[0] * 35, 4),
                np.round(sp.stats.theilslopes(s3_ac3)[0] * 35, 4),
                np.round(sp.stats.theilslopes(s3_tau1)[0] * 35, 4),
                np.round(sp.stats.theilslopes(s3_tau2)[0] * 35, 4),
                np.round(sp.stats.theilslopes(s3_tau3)[0] * 35, 4),
                np.round(sp.stats.theilslopes(s3_aod)[0] * 35, 4),
                np.round(sp.stats.theilslopes(s3_ssa)[0] * 35, 4),
                np.round(sp.stats.theilslopes(s3_asym)[0] * 35, 4),
                np.round(sp.stats.theilslopes(s3_h2o)[0] * 35, 4),
                np.round(sp.stats.theilslopes(s3_o3)[0] * 35, 4),
                np.round(sp.stats.theilslopes(s3_ssr)[0] * 35, 4),
                np.round(sp.stats.theilslopes(s4_Temperature)[0] * 35, 4),
                np.round(sp.stats.theilslopes(s4_Precipitation)[0] * 35, 7),
                np.round(sp.stats.theilslopes(s4_Evaporation)[0] * 35, 7),
                np.round(sp.stats.theilslopes(s4_Snow_Evaporation)[0] * 35, 7),
                np.round(sp.stats.theilslopes(s4_Snow_Density)[0] * 35, 4),
                np.round(sp.stats.theilslopes(s4_Sea_Ice_Fraction)[0] * 35, 4),
            ],
            Pval_95=[
                np.round(sp.stats.linregress(lengg, s3_ac1).pvalue, 3),
                np.round(sp.stats.linregress(lengg, s3_ac2).pvalue, 3),
                np.round(sp.stats.linregress(lengg, s3_ac3).pvalue, 3),
                np.round(sp.stats.linregress(lengg, s3_tau1).pvalue, 3),
                np.round(sp.stats.linregress(lengg, s3_tau2).pvalue, 3),
                np.round(sp.stats.linregress(lengg, s3_tau3).pvalue, 3),
                np.round(sp.stats.linregress(lengg, s3_aod).pvalue, 3),
                np.round(sp.stats.linregress(lengg, s3_ssa).pvalue, 3),
                np.round(sp.stats.linregress(lengg, s3_asym).pvalue, 3),
                np.round(sp.stats.linregress(lengg, s3_h2o).pvalue, 3),
                np.round(sp.stats.linregress(lengg, s3_o3).pvalue, 3),
                np.round(sp.stats.linregress(lengg, s3_ssr).pvalue, 3),
                np.round(sp.stats.linregress(lengg, s4_Temperature).pvalue, 3),
                np.round(sp.stats.linregress(lengg, s4_Precipitation).pvalue, 3),
                np.round(sp.stats.linregress(lengg, s4_Evaporation).pvalue, 3),
                np.round(sp.stats.linregress(lengg, s4_Snow_Evaporation).pvalue, 3),
                np.round(sp.stats.linregress(lengg, s4_Snow_Density).pvalue, 3),
                np.round(sp.stats.linregress(lengg, s4_Sea_Ice_Fraction).pvalue, 3),
            ],
        )


        df1 = pd.DataFrame(s2.data)
        csv_string1 = df1.to_csv(index=False)

        # Encode the CSV string as a base64 data URL
        b641 = base64.b64encode(csv_string1.encode()).decode()
        href1 = f'<a href="data:text/csv;base64,{b641}" download="contributions_lon{Xlong1}_{Xlong2}_lat{Xlati1}_lat{Xlati2}.csv">Get Contributions</a>'

        # Update the Div to display the download link
        download_link1.text = href1

        # Convert the data to a CSV string
        df2 = pd.DataFrame(s3.data)
        csv_string2 = df2.to_csv(index=False)

        # Encode the CSV string as a base64 data URL
        b642 = base64.b64encode(csv_string2.encode()).decode()
        href2 = f'<a href="data:text/csv;base64,{b642}" download="GDB_Drivers_timeserie_lon{Xlong1}_{Xlong2}_lat{Xlati1}_lat{Xlati2}.csv">Get Drivers</a>'

        # Update the Div to display the download link
        download_link2.text = href2

        # Convert the data to a CSV string
        df3 = pd.DataFrame(s4.data)
        csv_string3 = df3.to_csv(index=False)

        # Encode the CSV string as a base64 data URL
        b643 = base64.b64encode(csv_string3.encode()).decode()
        href3 = f'<a href="data:text/csv;base64,{b643}" download="Climate_timeseries_lon{Xlong1}_{Xlong2}_lat{Xlati1}_lat{Xlati2}.csv">Get Climate</a>'

        # Update the Div to display the download link
        download_link3.text = href3

        div1.text = f"""
        <div>
            <p style='font-family:Arial;font-size: 18px;  color: #06d8d8;'>
    Current position: <b>lon range</b>: {Xlong1:.2f}<sup>o</sup> --> {Xlong2:.2f}<sup>o</sup>, <b>lat range </b>: {Xlati1:.2f}<sup>o</sup> --> {Xlati2:.2f}<sup>o</sup>, <b>GDB</b>: {gdbdc.sel(lat=slice(Xlati1, Xlati2), lon=slice(Xlong1, Xlong2)).weighted(np.cos(np.deg2rad(wwq))).mean(("lat", "lon")).values:.2f} Wm<sup>-2</sup>decade<sup>-1</sup> </p>
        </div>
                    """


# this is for selection
# sourcebox.on_change('selected',getBoxDims)
p1.on_event(events.SelectionGeometry, getBoxDims)
# Add the callback to the image selection
s1.selected.on_change("image_indices", update_timeseries)
layout = column(
    row(
        row(p1_, p1),
        p3,
    ),
    row(row(div1), download_link1, download_link2, download_link3),
    row(p2, p4, data_table, div1x),
    row(text_area_input, column(Div(text=""""""))),
    background="#1a1a1a",
)
curdoc().add_root(layout)
curdoc().title = "GDB Drivers and Climate"
