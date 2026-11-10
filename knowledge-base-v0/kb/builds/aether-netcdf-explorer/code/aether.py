from bokeh.io import curdoc
from bokeh.layouts import column, row
from bokeh.models import (ColumnDataSource, TextInput, Select, Button, 
                         RadioButtonGroup, ColorBar, LinearColorMapper, Spinner,BoxSelectTool,TextAreaInput,
                         HoverTool, TapTool, Div, BasicTicker, Slider,TabPanel, Tabs,
                         Toggle, MultiChoice, DataTable, TableColumn,InlineStyleSheet, GlobalInlineStyleSheet,Range1d,
                         PointDrawTool, CustomAction, CustomJS,CustomJSHover,CrosshairTool,Span)
from bokeh.plotting import figure
from bokeh.palettes import (
    Viridis256, Plasma256, Inferno256, Magma256, Cividis256, Turbo256,Spectral11,
    RdBu11, linear_palette
)
from bokeh import events

import xarray as xr
import numpy as np
from scipy import stats
from scipy.signal import savgol_filter
import pandas as pd
import io
curdoc().theme = 'dark_minimal'
import cartopy.feature as cfeature
from scipy.stats import linregress, theilslopes
import cftime
import datetime


def cusj():
    num=1
    return CustomJSHover(code=f"""
    special_vars.indices = special_vars.indices.slice(0,{num})
    return special_vars.indices.includes(special_vars.index) ? " " : " hidden "
    """)
def hovfun(tltl):
    return """<div @hidden{custom} style="background-color: #fff0eb; padding: 5px; border-radius: 5px; box-shadow: 0px 0px 5px rgba(0,0,0,0.3);">        <font size="3" style="background-color: #fff0eb; padding: 5px; border-radius: 5px;"> """+tltl+""" <br> </font> </div> <style> :host { --tooltip-border: transparent;  /* Same border color used everywhere */ --tooltip-color: transparent; --tooltip-text: #2f2f2f;} </style> """

# ─── CSS ─────────────────────────────────────
base_variables = """ :host { /* CSS Custom Properties for easy theming */ --primary-color: #8b5cf6; --secondary-color: #06b6d4; --background-color: #1f2937; --surface-color: #343838; --text-color: #f9fafb; --accent-color: #f59e0b; --danger-color: #ef4444; --success-color: #10b981; --border-color: #4b5563; --hover-color: #6366f1; background: none !important; } """
tabs_style = InlineStyleSheet(css=""" /* Main tabs container */ :host { background: #2d2d2d !important; border-radius: 14px !important; padding: 8px !important; margin: 10px !important; box-shadow: 0 6px 20px #00ffe055, 0 2px 10px rgba(0, 0, 0, 0.3) !important; border: 1px solid rgba(0, 191, 255, 0.3) !important; } /* Tab navigation bar */ :host .bk-tabs-header { background: transparent !important; border-bottom: 2px solid #00bfff !important; margin-bottom: 8px !important; } /* Individual tab buttons */ :host .bk-tab { background: linear-gradient(135deg, #2d2d2d 0%, #3a3a3a 100%) !important; color: #00bfff !important; border: 1px solid #555 !important; border-radius: 8px 8px 0 0 !important; padding: 12px 20px !important; margin-right: 4px !important; font-family: 'Arial', sans-serif !important; font-weight: 600 !important; font-size: 0.95em !important; text-transform: uppercase !important; letter-spacing: 0.5px !important; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important; position: relative !important; overflow: hidden !important; } /* Tab hover effect */ :host .bk-tab:hover { background: linear-gradient(135deg, #dc1cdd 0%, #ff1493 100%) !important; color: #ffffff !important; border-color: #dc1cdd !important; box-shadow: 0 4px 15px rgba(220, 28, 221, 0.5) !important; transform: translateY(-2px) !important; } /* Active tab styling */ :host .bk-tab.bk-active { background: linear-gradient(135deg, #00bfff 0%, #0080ff 100%) !important; color: #000000 !important; border-color: #00bfff !important; box-shadow: 0 4px 20px rgba(0, 191, 255, 0.6), inset 0 2px 0 rgba(255, 255, 255, 0.3) !important; transform: translateY(-1px) !important; font-weight: 700 !important; } /* Active tab glow effect */ :host .bk-tab.bk-active::before { content: '' !important; position: absolute !important; top: 0 !important; left: 0 !important; right: 0 !important; bottom: 0 !important; background: linear-gradient(45deg, transparent 30%, rgba(255, 255, 255, 0.1) 50%, transparent 70%) !important; animation: shimmer 2s infinite !important; } @keyframes shimmer { 0% { transform: translateX(-100%); } 100% { transform: translateX(100%); } } /* Tab content area */ :host .bk-tab-content { background: transparent !important; padding: 16px !important; border-radius: 0 0 10px 10px !important; } /* Focus states for accessibility */ :host .bk-tab:focus { outline: 2px solid #00bfff !important; outline-offset: 2px !important; } /* Disabled tab state */ :host .bk-tab:disabled { background: #1a1a1a !important; color: #666 !important; cursor: not-allowed !important; opacity: 0.5 !important; } """)

gstyle = GlobalInlineStyleSheet(css=""" html, body, .bk, .bk-root {background-color: #343838; margin: 0; padding: 0; height: 100%; color: white; font-family: 'Consolas', 'Courier New', monospace; } .bk { color: white; } .bk-input, .bk-btn, .bk-select, .bk-slider-title, .bk-headers, .bk-label, .bk-title, .bk-legend, .bk-axis-label { color: white !important; } .bk-input::placeholder { color: #aaaaaa !important; } """)
style = InlineStyleSheet(css=""" .bk-btn { background-color: #00ffe0; color: #1e1e2e; font-weight: bold; border: 10px solid #00ffe0; border-radius: 6px; transform: rotate(0deg); box-shadow: none; transition: all 0.3s ease-in-out; } /* 🟦 Hover: #1e1e2e + rotate */ .bk-btn:hover { background-color: #1e1e2e; border-color: #1e1e2e; color: #00ffe0; transform: rotate(3deg); box-shadow: 0 0 15px 3px #00ffe0; } /* 🔴 Active (click hold): red + stronger rotate */ .bk-btn:active { background-color: red; border-color: red; transform: rotate(6deg); box-shadow: 0 0 15px 3px red; } """)
style2 = InlineStyleSheet(css=""" .bk-input { background-color: #1e1e1e; color: #d4d4d4; font-weight: 500; border: 1px solid #3c3c3c; border-radius: 5px; padding: 6px 10px; font-family: 'Consolas', 'Courier New', monospace; transition: all 0.2s ease; } /* Input Hover */ .bk-input:hover { background-color: #1e1e1e; color: #d4d4d4; font-weight: 500; border: 1.5px solid #ff3232;        /* Red border */ box-shadow: 0 0 9px 2px #ff3232cc;  /* Red glow */ border-radius: 5px; padding: 6px 10px; font-family: 'Consolas', 'Courier New', monospace; transition: all 0.2s ease; } /* Input Focus */ .bk-input:focus { background-color: #1e1e1e; color: #d4d4d4; font-weight: 500; border: 1.5px solid #ff3232; box-shadow: 0 0 11px 3px #ff3232dd; border-radius: 5px; padding: 6px 10px; font-family: 'Consolas', 'Courier New', monospace; transition: all 0.2s ease; } .bk-input:active { outline: none; background-color: #1e1e1e; color: #d4d4d4; font-weight: 500; border: 1.5px solid #ff3232; box-shadow: 0 0 14px 3px #ff3232; border-radius: 5px; padding: 6px 10px; font-family: 'Consolas', 'Courier New', monospace; transition: all 0.2s ease; } .bk-input:-webkit-autofill { background-color: #1e1e1e !important; color: #d4d4d4 !important; -webkit-box-shadow: 0 0 0px 1000px #1e1e1e inset !important; -webkit-text-fill-color: #d4d4d4 !important; } """)
style3 = InlineStyleSheet(css=""" .bk-btn { background-color: #00ffe0; color: #1e1e2e; font-weight: bold; border: none; border-radius: 8px; box-shadow: 0 2px 14px 0 #00ffe055; padding: 10px 26px; font-size: 1em; transition: background 0.18s, color 0.18s, box-shadow 0.2s; outline: none; cursor: pointer; } .bk-btn:hover { background: #22293b; color: #00ffe0; box-shadow: 0 0 20px 4px #00ffe0cc; } .bk-btn:active { background: #ff3131; color: #fff; box-shadow: 0 0 18px 3px #ff3131bb; } """)
slider_style = InlineStyleSheet(css=""" /* Host slider container */ :host { background: none !important; } /* Full track: set dark grey, but filled part will override with .noUi-connect */ :host .noUi-base, :host .noUi-target { background: #bfbfbf !important; } /* Highlighted portion of track */ :host .noUi-connect { background: #00ffe0; } /* Slider handle */ :host .noUi-handle { background: #343838; border: 2px solid #00ffe0; border-radius: 50%; width: 20px; height: 20px; } /* Handle hover/focus */ :host .noUi-handle:hover, :host .noUi-handle:focus { border-color: #ff2a68; box-shadow: 0 0 10px #ff2a6890; } /* Tooltip stepping value */ :host .noUi-tooltip { background: #343838; color: #00ffe0; font-family: 'Consolas', monospace; border-radius: 6px; border: 1px solid #00ffe0; } /* Filled (active) slider track */ :host .noUi-connect { background: linear-gradient(90deg, #ffea31 20%, #d810f7 100%) !important; /* greenish-cyan fade */ box-shadow: 0 0 10px #00ffe099 !important; } """)
multi_style = InlineStyleSheet(css=""" :host { /* CSS Custom Properties for easy theming */ --primary-color: #8b5cf6; --secondary-color: #06b6d4; --background-color: #1f2937; --surface-color: #343838; --text-color: #f9fafb; --accent-color: #f59e0b; --danger-color: #ef4444; background: none !important; } :host .choices__list--dropdown { background: var(--surface-color) !important; border: 1px solid var(--secondary-color) !important; border-radius: 8px !important; box-shadow: 0 10px 25px rgba(0,0,0,0.3) !important; } :host .choices__item--choice { color: var(--text-color) !important; padding: 12px 16px !important; border-bottom: 1px solid rgba(139, 92, 246, 0.2) !important; transition: all 0.2s ease !important; } :host .choices__item--choice:hover { background: var(--primary-color) !important; color: var(--background-color) !important; } :host .choices__item--selectable { background: linear-gradient(90deg, #ffb028 20%, #ff4f4f 100%) !important; color: var(--background-color) !important; border-radius: 6px !important; padding: 6px 12px !important; margin: 3px !important; font-weight: 600 !important; } :host .choices__inner { background: none !important; color: var(--text-color) !important; border: 1px solid lime !important; font-size: 14px !important; } """)
button_style = InlineStyleSheet(css=base_variables + """ :host button { background: linear-gradient(135deg, var(--primary-color), var(--secondary-color)) !important; color: white !important; border: none !important; border-radius: 6px !important; padding: 10px 20px !important; font-size: 14px !important; font-weight: 600 !important; cursor: pointer !important; transition: all 0.2s ease !important; box-shadow: 0 2px 4px rgba(0,0,0,0.1) !important; } :host button:hover { transform: translateY(-1px) !important; box-shadow: 0 4px 8px rgba(0,0,0,0.2) !important; background: linear-gradient(135deg, var(--hover-color), var(--primary-color)) !important; } :host button:active { transform: translateY(0) !important; box-shadow: 0 2px 4px rgba(0,0,0,0.1) !important; } :host button:disabled { background: #6b7280 !important; cursor: not-allowed !important; transform: none !important; box-shadow: none !important; } """)
multi_style = InlineStyleSheet(css=""" /* Outer widget container */ :host { background: #181824 !important; border-radius: 14px !important; padding: 16px !important; box-shadow: 0 4px 20px #0008 !important; } /* Title styling */ :host .bk-input-group label, :host .bk-multichoice-title { color: #00ffe0 !important; font-size: 1.18em !important; font-family: 'Fira Code', monospace; font-weight: bold !important; margin-bottom: 10px !important; letter-spacing: 1px !important; text-shadow: 0 2px 12px #00ffe088, 0 1px 4px #181824; } /* The input field when closed */ :host .choices__inner { background: #23233c !important; color: #f9fafb !important; border: 2px solid #06b6d4 !important; border-radius: 8px !important; font-size: 1.05em !important; transition: border 0.1s, box-shadow 0.1s; box-shadow: none !important; } /* Glow on hover/focus of input */ :host .choices__inner:hover, :host .choices__inner:focus-within { border-color: #ff3049 !important; box-shadow: 0 0 0 2px #ff304999, 0 0 16px #ff3049cc !important; outline: none !important; } /* Dropdown list */ :host .choices__list--dropdown { background: #181824 !important; border: 1.5px solid #06b6d4 !important; border-radius: 8px !important; box-shadow: 0 10px 32px #000c !important; } /* Items in the dropdown */ :host .choices__item--choice { color: #f9fafb !important; padding: 12px 16px !important; transition: all 0.15s; border-bottom: 1px solid #28284666 !important; } :host .choices__item--choice:hover { background: #8b5cf6 !important; color: #1f2937 !important; } /* Active selected items in the box */ :host .choices__item--selectable { background: linear-gradient(90deg, #ffb028 20%, #ff4f4f 100%) !important; color: #181824 !important; border-radius: 6px !important; font-weight: 600 !important; margin: 2px 4px !important; padding: 6px 14px !important; box-shadow: 0 1px 6px #0005; } """)
fancy_div_style = InlineStyleSheet(css=""" :host { position: relative; background: #21233a; color: #fff; border-radius: 12px; padding: 18px 28px; text-align: center; overflow: hidden; box-shadow: 0 6px 10px rgba(197, 153, 10, 0.2); } :host::after { content: ''; position: absolute; top: 0; left: -80%; width: 200%; height: 100%; background: linear-gradient(120deg, transparent 40%, rgba(255, 252, 71, 0.416) 50%, transparent 60%); animation: shimmer 2.2s infinite; pointer-events: none; border-radius: inherit; } @keyframes shimmer { 0%   { left: -80%; } 100% { left: 100%; } } """)

# ─── LOADING SPINNER HTML ─────────────────────────────────────

radio_style = InlineStyleSheet(css=""" /* Outer container */ :host { background: #181824 !important; border-radius: 16px !important; padding: 22px 22px 18px 22px !important; box-shadow: 0 4px 18px #0008 !important; max-width: 600px !important; } /* Title */ :host .bk-input-group label, :host .bk-radiobuttongroup-title { color: #f59e0b !important; font-size: 1.16em !important; font-family: 'Fira Code', monospace; font-weight: bold !important; margin-bottom: 16px !important; text-shadow: 0 2px 10px #f59e0b99; letter-spacing: 0.5px; } /* Button group: wrap on small screens */ :host .bk-btn-group { display: flex !important; gap: 18px !important; flex-wrap: wrap !important; justify-content: flex-start; margin-bottom: 6px; } /* Each radio button - pill shape, full text, no ellipsis */ :host button.bk-btn { background: #23233c !important; color: #f9fafb !important; border: 2.5px solid #f59e0b !important; border-radius: 999px !important; padding: 0.7em 2.2em !important; min-width: 120px !important; font-size: 1.09em !important; font-family: 'Fira Code', monospace; font-weight: 600 !important; transition: border 0.13s, box-shadow 0.14s, color 0.12s, background 0.13s; box-shadow: 0 2px 10px #0002 !important; cursor: pointer !important; outline: none !important; white-space: nowrap !important; overflow: visible !important; text-overflow: unset !important; } /* Orange glow on hover */ :host button.bk-btn:hover:not(.bk-active) { border-color: #ffa733 !important; color: #ffa733 !important; box-shadow: 0 0 0 2px #ffa73399, 0 0 13px #ffa73388 !important; background: #2e2937 !important; } /* Red glow on active/focus */ :host button.bk-btn:focus, :host button.bk-btn.bk-active { border-color: #ff3049 !important; color: #ff3049 !important; background: #322d36 !important; box-shadow: 0 0 0 2px #ff304999, 0 0 19px #ff304988 !important; } /* Remove focus outline */ :host button.bk-btn:focus { outline: none !important; } """)
base_variables = """ :host { /* CSS Custom Properties for easy theming */ --primary-color: #8b5cf6; --secondary-color: #06b6d4; --background-color: #1f2937; --surface-color: #343838; --text-color: #f9fafb; --accent-color: #f59e0b; --danger-color: #ef4444; --success-color: #10b981; --border-color: #4b5563; --hover-color: #6366f1; background: none !important; } """
textarea_style  = InlineStyleSheet(css=base_variables + """ :host textarea { background: var(--surface-color) !important; color: var(--text-color) !important; border: 1px solid var(--border-color) !important; border-radius: 6px !important; padding: 10px 12px !important; font-size: 14px !important; font-family: inherit !important; transition: all 0.2s ease !important; resize: vertical !important; } :host textarea:focus { outline: none !important; border-color: var(--primary-color) !important; box-shadow: 0 0 0 2px rgba(139, 92, 246, 0.2) !important; } :host textarea::placeholder { color: #9ca3af !important; opacity: 0.7 !important; } """)

heatmap_stats_div = Div(text="", width=1000, styles={'color': 'orange', 'font-size': '18px', 'margin-bottom': '10px'})

def get_valid_savgol_window(window, order, npts):
    # Ensure window is odd and at most npts
    window = min(window, npts)
    if window % 2 == 0:
        window -= 1
    if window < order + 2:
        window = order + 2
        if window % 2 == 0:
            window += 1
    if window > npts:
        window = npts if npts % 2 == 1 else npts - 1
    if window < 3 or window > npts:
        return None  # Not enough points for filtering
    return window

def safe_sel(data, dim, val):
    try:
        # Only select if dim is a real coordinate or index
        if dim not in data.coords and dim not in data.indexes:
            print(f"[safe_sel] SKIP: Cannot select on dim '{dim}' (not a coordinate or index).")
            return data
        coord_vals = data[dim].values
        # Convert value to correct type
        try:
            if coord_vals.dtype.kind in ['i', 'u', 'f']:
                val = type(coord_vals[0])(val)
            elif np.issubdtype(coord_vals.dtype, np.datetime64):
                val = np.datetime64(val)
        except Exception:
            pass  # fallback to original if conversion fails
        # Use nearest if exact value not present
        try:
            return data.sel({dim: val})
        except KeyError:
            return data.sel({dim: val}, method="nearest")
    except Exception as e:
        print(f"safe_sel ERROR for dim={dim}, value={val}: {e}")
        return data

# Create dimension selector class
class DimensionSelector:
    def __init__(self, callback=None):
        self.time_dim = Select(title="Time Dimension:", value="None", options=["None"], stylesheets = [style2])
        self.fourth_dim = Select(title="4th Dimension:", value="None", options=["None"], stylesheets = [style2])
        self.fourth_value = Select(title="4th Value:", value="None", options=["None"], stylesheets = [style2])
        self.fifth_dim = Select(title="5th Dimension:", value="None", options=["None"], stylesheets = [style2])
        self.fifth_value = Select(title="5th Value:", value="None", options=["None"], stylesheets = [style2])
        
        self.time_dim.on_change('value', self._value_changed)
        self.fourth_dim.on_change('value', self._update_fourth_values)
        self.fifth_dim.on_change('value', self._update_fifth_values)
        self.fourth_value.on_change('value', self._value_changed)
        self.fifth_value.on_change('value', self._value_changed)
        
        self.dataset = None
        self.update_callback = callback
    
    def _update_fourth_values(self, attr, old, new):
        if new != "None" and self.dataset is not None:
            values = [str(v) for v in self.dataset[new].values]
            self.fourth_value.options = values
            self.fourth_value.value = values[0]
        else:
            self.fourth_value.options = ["None"]
            self.fourth_value.value = "None"
    
    def _update_fifth_values(self, attr, old, new):
        if new != "None" and self.dataset is not None:
            values = [str(v) for v in self.dataset[new].values]
            self.fifth_value.options = values
            self.fifth_value.value = values[0]
        else:
            self.fifth_value.options = ["None"]
            self.fifth_value.value = "None"
    
    def _value_changed(self, attr, old, new):
        if self.update_callback:
            self.update_callback(attr, old, new)
    
    def update_dimensions(self, dataset, var_name):
        self.dataset = dataset
        dims = list(dataset[var_name].dims)

        # Identify all "time-like" dims (e.g., 'time', 'year', 'date')
        time_dims = [d for d in dims if any(key in d.lower() for key in ['time', 'year', 'date', 'month', 'day', 'hour', 'minute', 'second','index'])]
        self.time_dim.options = ["None"] + time_dims
        if 'time' in time_dims:
            self.time_dim.value = 'time'
        elif time_dims:
            self.time_dim.value = time_dims[0]
        else:
            self.time_dim.value = "None"

        # Exclude time/lat/lon dims for other selectors
        spatial_keywords = ['lat', 'latitude', 'lon', 'longitude']
        non_spatial_dims = [d for d in dims if d.lower() not in spatial_keywords + time_dims]

        # Auto-select 4th and 5th dim if available, else "None"
        self.fourth_dim.options = ["None"] + (non_spatial_dims[0:1] if len(non_spatial_dims) > 0 else [])
        self.fifth_dim.options = ["None"] + (non_spatial_dims[1:2] if len(non_spatial_dims) > 1 else [])

        self.fourth_dim.value = non_spatial_dims[0] if len(non_spatial_dims) > 0 else "None"
        self.fifth_dim.value = non_spatial_dims[1] if len(non_spatial_dims) > 1 else "None"

    
    def get_selection(self):
        return {
            'time_dim': self.time_dim.value,
            'fourth_dim': self.fourth_dim.value,
            'fourth_value': self.fourth_value.value,
            'fifth_dim': self.fifth_dim.value,
            'fifth_value': self.fifth_value.value
        }
    
    def get_layout(self):
        return column(
            self.time_dim,row(
            row(self.fourth_dim, self.fourth_value),
            row(self.fifth_dim, self.fifth_value),),
            styles={
                # 'background-color': '#0f005a',
                # 'padding': '10px',
                # 'border-radius': '5px',
                # 'margin': '5px'
            }
        )
    
    def set_update_callback(self, callback):
        self.update_callback = callback

# Initialize data sources
source = ColumnDataSource(data=dict(image=[], x=[], y=[], dw=[], dh=[]))
timeseries_source = ColumnDataSource(data=dict(time=[], value=[], filtered=[], trend=[], hidden=[]))
timeseries_source22 = ColumnDataSource(data=dict(time=[], value=[]))
atimeseries_source = ColumnDataSource(data=dict(time=[], value=[], filtered=[], trend=[], hidden=[]))

annual_source = ColumnDataSource(data=dict(month=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'], value=[0]*12))
seasonal_source = ColumnDataSource(data=dict(
    season=['DJF', 'MAM', 'JJA', 'SON'],
    value=[0, 0, 0, 0]
))
stats_table_source = ColumnDataSource(data=dict(region=[], value=[]))

# Add box selection source and tool
sourcebox = ColumnDataSource( data=dict( x=[], y=[], width=[], height=[], color=['grey'], alpha=[0.35], ),)

# Add click marker source
click_marker_source = ColumnDataSource({
    'x': [0], 
    'y': [0], 
    'size': [20],
    'alpha': [1.0]
})

# Global variables
dataset = None
callback_id = None
current_point = None  # Store current point

# Create dimension selector
dim_selector = DimensionSelector()

# Create widgets
file_path = TextInput(title="NetCDF File Path:", value="", width=300, stylesheets=[style2])
load_button = Button(label="Load File", button_type="primary", stylesheets=[button_style])
var_select = Select(title="Variable:", options=[], stylesheets=[style2])
x_dim_select = Select(title="X Dimension:", options=[], stylesheets=[style2])
y_dim_select = Select(title="Y Dimension:", options=[], stylesheets=[style2])
time_slider = Slider(title="Time", start=0, end=1, value=0, step=1, stylesheets = [slider_style])
time_select = MultiChoice(title="Select Dates:", value=[], options=[], width=350, max_items=1, stylesheets=[multi_style])
play_button = Toggle(label="▶ Play", button_type="success", width=100, stylesheets=[button_style])
colormap_select = Select(title="Colormap:", 
                        options=['RdBu', 'Viridis', 'Spectral', 'Plasma', 'Inferno', 'Magma', 'Cividis', 'Turbo'],
                        value='Viridis', styles={'color': 'silver'}, stylesheets=[style2])
window_spinner = Spinner(title="Window Size:", low=5, high=501, step=2, value=121, width=70, stylesheets=[style2])
order_spinner = Spinner(title="Poly Order:", low=1, high=10, step=1, value=3, width=70, stylesheets=[style2])
min_spinner = Spinner(title="Min Value:", width=90, stylesheets=[style2])
max_spinner = Spinner(title="Max Value:", width=90, stylesheets=[style2])
trend_method = RadioButtonGroup(labels=["OLS", "Theil-Sen"], active=0)
stats_div = Div(text="", styles={'z-index': '10','margin-left': '270px','margin-top': '42px', 'color': 'orange', 'font-size': '16px','width': '800px',})

# Create stats table
stats_table = DataTable(
    source=stats_table_source,
    columns=[
        TableColumn(field='region', title='Region', width=150),
        TableColumn(field='value', title='Average Value', width=100)
    ],
    width=250,
    height=120,
    index_position=None,
    styles={
        'color': 'silver',
        'background-color': '#2e3131',
        'font-size': '12px',
        'border': '1px solid silver'
    }
)


RdBu256 = linear_palette(RdBu11, 11)
def get_palette(name):
    if name == 'Viridis':
        return Viridis256
    elif name == 'Plasma':
        return Plasma256
    elif name == 'Spectral':
        return Spectral11
    elif name == 'Inferno':
        return Inferno256
    elif name == 'Magma':
        return Magma256
    elif name == 'Cividis':
        return Cividis256
    elif name == 'Turbo':
        return Turbo256
    elif name == 'RdBu':
        return RdBu256
    else:
        return Viridis256

                        


def minmax_spinner_callback(attr, old, new):
    update_color_mapper(min_spinner.value, max_spinner.value)


def adjust_coordinates(dataset):
    """Adjust lat/lon coordinates if they start from 0"""
    # if "lat" in dataset.coords and dataset["lat"].min() >= 0:
    #     dataset = dataset.assign_coords(lat=dataset["lat"] - 90)
    if "lon" in dataset.coords and dataset["lon"].min() >= 0:
        dataset = dataset.assign_coords(lon=dataset["lon"] - 180)
    return dataset


def robust_parse_time_axis(time_values):
    # Handle numpy datetime64 and pandas-compatible
    if np.issubdtype(type(time_values[0]), np.datetime64):
        times = pd.to_datetime(time_values)
        is_datetime = True
        freq_unit = detect_frequency(times)
    # Handle cftime objects
    elif isinstance(time_values[0], cftime.DatetimeNoLeap) or isinstance(time_values[0], cftime.DatetimeGregorian) or "cftime" in str(type(time_values[0])):
        try:
            # Attempt to convert to pandas datetime (will fail for non-Gregorian)
            times = pd.to_datetime([t.strftime("%Y-%m-%d") for t in time_values])
            is_datetime = True
            freq_unit = detect_frequency(times)
        except Exception:
            # Fallback: use numeric axis (e.g., years since start)
            base_year = time_values[0].year
            times = np.array([t.year + t.month/12 + t.day/365 for t in time_values])
            is_datetime = False
            freq_unit = "years"
    elif np.issubdtype(type(time_values[0]), np.integer) or np.issubdtype(type(time_values[0]), np.floating):
        if np.all((time_values > 1800) & (time_values < 2100)):
            times = pd.to_datetime([f"{int(y)}-01-01" for y in time_values])
            is_datetime = True
            freq_unit = "years"
        else:
            times = time_values
            is_datetime = False
            freq_unit = "steps"
    else:
        times = np.arange(len(time_values))
        is_datetime = False
        freq_unit = "steps"
    return times, freq_unit, is_datetime


def update_timeseries(event):
    if dataset is None:
        return
        
    global current_point
    current_point = (event.x, event.y)
    
    # Update click marker with persistent visibility
    click_marker_source.data.update({
        'x': [event.x],
        'y': [event.y]
    })
    
    update_current_timeseries()


def select_with_type_cast(data, dim, val):
    coord_vals = data[dim].values
    # Convert value to correct type
    try:
        # If numbers (int/float)
        if coord_vals.dtype.kind in ['i', 'u', 'f']:
            val = type(coord_vals[0])(val)
        # If datetime
        elif np.issubdtype(coord_vals.dtype, np.datetime64):
            val = np.datetime64(val)
        # else keep as string
    except Exception:
        pass  # fallback to original if conversion fails

    # Use nearest if exact value not present
    try:
        return data.sel({dim: val})
    except KeyError:
        return data.sel({dim: val}, method="nearest")


def update_current_timeseries():
    if dataset is None or current_point is None:
        return
        
    x, y = current_point
    data = dataset[var_select.value]
    
    # Get dimension selections
    dims = dim_selector.get_selection()
    
    # Apply dimension selections for non-time dimensions
    if dims['fourth_dim'] != 'None':
        dim = dims['fourth_dim']
        val = dims['fourth_value']
        # Get actual type from coordinate array
        coord_vals = data[dim].values
        # Convert string input to correct type
        try:
            if coord_vals.dtype.kind in ['i', 'u', 'f']:
                val = type(coord_vals[0])(val)
            elif np.issubdtype(coord_vals.dtype, np.datetime64):
                val = np.datetime64(val)
            # else keep as string
        except Exception:
            pass  # fallback to original if conversion fails
        data = data.sel({dim: val})

    if dims['fifth_dim'] != 'None':
        dim = dims['fifth_dim']
        val = dims['fifth_value']
        # Get actual type from coordinate array
        coord_vals = data[dim].values
        # Convert string input to correct type
        try:
            if coord_vals.dtype.kind in ['i', 'u', 'f']:
                val = type(coord_vals[0])(val)
            elif np.issubdtype(coord_vals.dtype, np.datetime64):
                val = np.datetime64(val)
            # else keep as string
        except Exception:
            pass  # fallback to original if conversion fails
        data = data.sel({dim: val})

    # Get time series at clicked point
    ts = data.sel({
        x_dim_select.value: x,
        y_dim_select.value: y
    }, method='nearest')
    
    # Handle time dimension
    # Handle time dimension
    # Handle time dimension
    if dims['time_dim'] != 'None':
        times_raw = dataset[dims['time_dim']].values

        if np.issubdtype(times_raw.dtype, np.datetime64):
            times = pd.to_datetime(times_raw)
            freq_unit = detect_frequency(times)
            is_datetime = True
        elif np.issubdtype(times_raw.dtype, np.integer) or np.issubdtype(times_raw.dtype, np.floating):
            # Years if plausible
            if np.all((times_raw > 1800) & (times_raw < 2100)):
                times = pd.to_datetime([f"{int(year)}-01-01" for year in times_raw])
                freq_unit = "years"
                is_datetime = True
            # Steps if strictly monotonically increasing by 1, and small (<200)
            elif np.all(times_raw == np.arange(times_raw[0], times_raw[0]+len(times_raw))):
                times = times_raw  # Keep as numeric index
                freq_unit = "steps"
                is_datetime = False
            else:
                # Try datetime conversion, fallback to numeric
                converted = pd.to_datetime(times_raw, errors='coerce')
                if pd.isnull(converted).all():
                    times = times_raw
                    freq_unit = "steps"
                    is_datetime = False
                else:
                    times = converted
                    freq_unit = detect_frequency(times)
                    is_datetime = True
        else:
            # Last resort: try to parse as datetime, else use as index
            converted = pd.to_datetime(times_raw, errors='coerce')
            if pd.isnull(converted).all():
                times = np.arange(len(times_raw))
                freq_unit = "steps"
                is_datetime = False
            else:
                times = converted
                freq_unit = detect_frequency(times)
                is_datetime = True

        values = ts.values

        if freq_unit == "months":
            df = pd.DataFrame({'value': values}, index=times)
            monthly_means = df.groupby(df.index.month)['value'].transform('mean')
            avalues = df['value'] - monthly_means
        else:
            avalues = values - np.nanmean(values)
        timeseries_source.data = dict(time=times, value=values, hidden=[False]*len(times))
        atimeseries_source.data = dict(time=times, value=avalues, hidden=[False]*len(times))



        if len(atimeseries_source.data["time"]) > 1:
            atimeseries_source22.data = dict(
                time=[
                    atimeseries_source.data["time"][0],
                    atimeseries_source.data["time"][-1]
                ],
                value=[
                    atimeseries_source.data["value"][0],
                    atimeseries_source.data["value"][-1]
                ]
            )
        else:
            atimeseries_source22.data = dict(time=[], value=[])



        # timeseries_source.yaxis.axis_label = ylabel
        x_min = times.min()
        x_max = times.max()
        # After updating timeseries_src.data and after calculating y_min/y_max:
        if len(values) > 0 and np.any(np.isfinite(values)):
            y_min = np.nanmin(values)
            y_max = np.nanmax(values)
            y_pad = (y_max - y_min) * 0.05 if y_max != y_min else 1.0
            timeseries.y_range = Range1d(start=y_min - y_pad, end=y_max + y_pad)
            timeseries.x_range = Range1d(start=x_min, end=x_max)

        else:
            timeseries.y_range = Range1d(start=0, end=1)
        if len(avalues) > 0 and np.any(np.isfinite(avalues)):
            y_min = np.nanmin(avalues)
            y_max = np.nanmax(avalues)
            y_pad = (y_max - y_min) * 0.05 if y_max != y_min else 1.0
            atimeseries.y_range = Range1d(start=y_min - y_pad, end=y_max + y_pad)
            atimeseries.x_range = Range1d(start=x_min, end=x_max)

        else:
            atimeseries.y_range = Range1d(start=-1, end=1)
        
        # Apply Savitzky-Golay filter
        window = int(window_spinner.value)
        order = int(order_spinner.value)
        npts = len(values)

        window = get_valid_savgol_window(window, order, npts)
        if window is not None and npts >= window:
            try:
                filtered = savgol_filter(np.nan_to_num(values, nan=0.0), window, order)
            except Exception as e:
                filtered = values
        else:
            filtered = values  # Not enough points to filter

        
        # Calculate trend
        x_trend = np.arange(len(times))
        mask = ~np.isnan(values)
        if trend_method.active == 0:  # OLS
            slope, intercept, r_value, p_value, std_err = stats.linregress(x_trend[mask], values[mask])
        else:  # Theil-Sen
            slope, intercept, lo_slope, up_slope = stats.theilslopes(values[mask], x_trend[mask], 0.95)
            tau, p_value = stats.kendalltau(x_trend[mask], values[mask])
        
        trend_line = slope * x_trend + intercept
        




                # Apply Savitzky-Golay filter
        window = int(window_spinner.value)
        order = int(order_spinner.value)
        npts = len(avalues)

        window = get_valid_savgol_window(window, order, npts)
        if window is not None and npts >= window:
            try:
                afiltered = savgol_filter(np.nan_to_num(avalues, nan=0.0), window, order)
            except Exception as e:
                afiltered = avalues
        else:
            afiltered = avalues  # Not enough points to filter

        
        # Calculate trend
        x_trend = np.arange(len(times))
        mask = ~np.isnan(avalues)
        if trend_method.active == 0:  # OLS
            aslope, aintercept, r_value, ap_value, std_err = stats.linregress(x_trend[mask], avalues[mask])
        else:  # Theil-Sen
            aslope, aintercept, lo_slope, up_slope = stats.theilslopes(avalues[mask], x_trend[mask], 0.95)
            tau, ap_value = stats.kendalltau(x_trend[mask], avalues[mask])
        
        atrend_line = aslope * x_trend + aintercept
        # Update all plots
        timeseries_source.data = dict(
            time=times,
            value=values,
            filtered=filtered,
            trend=trend_line,
            hidden=[False] * len(times)  # Show all points initially
        )
        atimeseries_source.data = dict(
            time=times,
            value=avalues,
            filtered=afiltered,
            trend=atrend_line,
            hidden=[False] * len(times)  # Show all points initially
        )



        if len(atimeseries_source.data["time"]) > 1:
            atimeseries_source22.data = dict(
                time=[
                    atimeseries_source.data["time"][0],
                    atimeseries_source.data["time"][-1]
                ],
                value=[
                    atimeseries_source.data["value"][0],
                    atimeseries_source.data["value"][-1]
                ]
            )
        else:
            atimeseries_source22.data = dict(time=[], value=[])

        timeseries_source22.data = dict(
            time=[times[0], times[-1]],
            value=[values[0], values[-1]],
        )

        if freq_unit == "months":
            update_cycles(times, values)

        if freq_unit != "months":
            annual_cycle.visible = False
        if freq_unit == "months":
            annual_cycle.visible = True        
        
        stats_div.text = f"""
        Point: ({x:.2f}, {y:.2f}) | Trend: {slope:.4f} per time step | P-value: {p_value:.4f}
        """
    else:
        # If no time dimension, just show the point value
        value = float(ts.values)
        stats_div.text = f"""
        Point: ({x:.2f}, {y:.2f}) | Value: {value:.2e}
        """

def spinner_callback(attr, old, new):
    update_current_timeseries()

def animate_update():
    if dataset is None:
        return
        
    time_slider.value = (time_slider.value + 1) % (time_slider.end + 1)

def animate(active):
    global callback_id
    if active:
        play_button.label = "⏸ Pause"
        callback_id = curdoc().add_periodic_callback(animate_update, 200)
    else:
        play_button.label = "▶ Play"
        if callback_id is not None:
            curdoc().remove_periodic_callback(callback_id)

def update_box_selection(event):#attrname,old,new
    print('new----------',event.__dict__['geometry'])
    # xl = sourcebox.data['x'][0]-sourcebox.data['width'][0]/2
    # xr = sourcebox.data['x'][0]+sourcebox.data['width'][0]/2
    # yl = sourcebox.data['y'][0]-sourcebox.data['height'][0]/2
    # yu = sourcebox.data['y'][0]+sourcebox.data['height'][0]/2
    if event.__dict__['geometry']['type'] == 'rect':
        mie = event.__dict__['geometry']
        if "x0" not in mie:
            xl = mie["x"]
            xr = mie["x"]
            yl = mie["y"]
            yu = mie["y"]
        else:    
            xl = mie["x0"]
            xr = mie["x1"]
            yl = mie["y0"]
            yu = mie["y1"]    
        if dataset is None:
            return
            
        data = dataset[var_select.value]
        
        # Get dimension selections
        dims = dim_selector.get_selection()
        
        # Apply dimension selections for non-time dimensions
        if dims['fourth_dim'] != 'None':
            data = safe_sel(data, dims['fourth_dim'], dims['fourth_value'])
        if dims['fifth_dim'] != 'None':
            data = safe_sel(data, dims['fifth_dim'], dims['fifth_value'])
        
        # Get time series for the selected area
        ts = data.sel({
            x_dim_select.value: slice(xl, xr),
            y_dim_select.value: slice(yl, yu)
        }).mean(dim=[x_dim_select.value, y_dim_select.value])
        
        # Handle time dimension
        if dims['time_dim'] != 'None':
            times_raw = dataset[dims['time_dim']].values

            if np.issubdtype(times_raw.dtype, np.datetime64):
                times = pd.to_datetime(times_raw)
                freq_unit = detect_frequency(times)
                is_datetime = True
            elif np.issubdtype(times_raw.dtype, np.integer) or np.issubdtype(times_raw.dtype, np.floating):
                # Years if plausible
                if np.all((times_raw > 1800) & (times_raw < 2100)):
                    times = pd.to_datetime([f"{int(year)}-01-01" for year in times_raw])
                    freq_unit = "years"
                    is_datetime = True
                # Steps if strictly monotonically increasing by 1, and small (<200)
                elif np.all(times_raw == np.arange(times_raw[0], times_raw[0]+len(times_raw))):
                    times = times_raw  # Keep as numeric index
                    freq_unit = "steps"
                    is_datetime = False
                else:
                    # Try datetime conversion, fallback to numeric
                    converted = pd.to_datetime(times_raw, errors='coerce')
                    if pd.isnull(converted).all():
                        times = times_raw
                        freq_unit = "steps"
                        is_datetime = False
                    else:
                        times = converted
                        freq_unit = detect_frequency(times)
                        is_datetime = True
            else:
                # Last resort: try to parse as datetime, else use as index
                converted = pd.to_datetime(times_raw, errors='coerce')
                if pd.isnull(converted).all():
                    times = np.arange(len(times_raw))
                    freq_unit = "steps"
                    is_datetime = False
                else:
                    times = converted
                    freq_unit = detect_frequency(times)
                    is_datetime = True

            values = ts.values
            if freq_unit == "months":
                df = pd.DataFrame({'value': values}, index=times)
                monthly_means = df.groupby(df.index.month)['value'].transform('mean')
                avalues = df['value'] - monthly_means
            else:
                avalues = values - np.nanmean(values)
            timeseries_source.data = dict(time=times, value=values, hidden=[False]*len(times))
            atimeseries_source.data = dict(time=times, value=avalues, hidden=[False]*len(times))


            if len(atimeseries_source.data["time"]) > 1:
                atimeseries_source22.data = dict(
                    time=[
                        atimeseries_source.data["time"][0],
                        atimeseries_source.data["time"][-1]
                    ],
                    value=[
                        atimeseries_source.data["value"][0],
                        atimeseries_source.data["value"][-1]
                    ]
                )
            else:
                atimeseries_source22.data = dict(time=[], value=[])


            # timeseries_source.yaxis.axis_label = ylabel
            x_min = times.min()
            x_max = times.max()
            # After updating timeseries_src.data and after calculating y_min/y_max:
            if len(values) > 0 and np.any(np.isfinite(values)):
                y_min = np.nanmin(values)
                y_max = np.nanmax(values)
                y_pad = (y_max - y_min) * 0.05 if y_max != y_min else 1.0
                timeseries.y_range = Range1d(start=y_min - y_pad, end=y_max + y_pad)
                timeseries.x_range = Range1d(start=x_min, end=x_max)

            else:
                timeseries.y_range = Range1d(start=0, end=1)
            if len(avalues) > 0 and np.any(np.isfinite(avalues)):
                y_min = np.nanmin(avalues)
                y_max = np.nanmax(avalues)
                y_pad = (y_max - y_min) * 0.05 if y_max != y_min else 1.0
                atimeseries.y_range = Range1d(start=y_min - y_pad, end=y_max + y_pad)
                atimeseries.x_range = Range1d(start=x_min, end=x_max)

            else:
                atimeseries.y_range = Range1d(start=-1, end=1)
            timeseries_source.data = dict(time=times, value=values, hidden=[False]*len(times))
            # timeseries_source.yaxis.axis_label = ylabel
            x_min = times.min()
            x_max = times.max()
            # After updating timeseries_src.data and after calculating y_min/y_max:
            if len(values) > 0 and np.any(np.isfinite(values)):
                y_min = np.nanmin(values)
                y_max = np.nanmax(values)
                y_pad = (y_max - y_min) * 0.05 if y_max != y_min else 1.0
                timeseries.y_range = Range1d(start=y_min - y_pad, end=y_max + y_pad)
                timeseries.x_range = Range1d(start=x_min, end=x_max)

            else:
                timeseries.y_range = Range1d(start=0, end=1)
            # Apply Savitzky-Golay filter
            window = int(window_spinner.value)
            order = int(order_spinner.value)
            npts = len(values)

            window = get_valid_savgol_window(window, order, npts)
            if window is not None and npts >= window:
                try:
                    filtered = savgol_filter(np.nan_to_num(values, nan=0.0), window, order)
                except Exception as e:
                    filtered = values
            else:
                filtered = values

            
            # Calculate trend
            x_trend = np.arange(len(times))
            mask = ~np.isnan(values)
            print('mask',mask)
            print('x_trend',x_trend)
            print('values',values)
            if trend_method.active == 0:  # OLS
                slope, intercept, r_value, p_value, std_err = stats.linregress(x_trend[mask], values[mask])
            else:  # Theil-Sen
                slope, intercept, lo_slope, up_slope = stats.theilslopes(values[mask], x_trend[mask], 0.95)
                tau, p_value = stats.kendalltau(x_trend[mask], values[mask])
            
            trend_line = slope * x_trend + intercept
            



            window = int(window_spinner.value)
            order = int(order_spinner.value)
            npts = len(avalues)

            window = get_valid_savgol_window(window, order, npts)
            if window is not None and npts >= window:
                try:
                    afiltered = savgol_filter(np.nan_to_num(avalues, nan=0.0), window, order)
                except Exception as e:
                    afiltered = avalues
            else:
                afiltered = avalues  # Not enough points to filter

            
            # Calculate trend
            x_trend = np.arange(len(times))
            mask = ~np.isnan(avalues)
            if trend_method.active == 0:  # OLS
                aslope, aintercept, r_value, ap_value, std_err = stats.linregress(x_trend[mask], avalues[mask])
            else:  # Theil-Sen
                aslope, aintercept, lo_slope, up_slope = stats.theilslopes(avalues[mask], x_trend[mask], 0.95)
                tau, ap_value = stats.kendalltau(x_trend[mask], avalues[mask])
            
            atrend_line = aslope * x_trend + aintercept



            # Update all plots
            timeseries_source.data = dict(
                time=times,
                value=values,
                filtered=filtered,
                trend=trend_line,
                hidden=[False]*len(times),
            )
            atimeseries_source.data = dict(
            time=times,
            value=avalues,
            filtered=afiltered,
            trend=atrend_line,
            hidden=[False] * len(times)  # Show all points initially
        )
            


            if len(atimeseries_source.data["time"]) > 1:
                atimeseries_source22.data = dict(
                    time=[
                        atimeseries_source.data["time"][0],
                        atimeseries_source.data["time"][-1]
                    ],
                    value=[
                        atimeseries_source.data["value"][0],
                        atimeseries_source.data["value"][-1]
                    ]
                )
            else:
                atimeseries_source22.data = dict(time=[], value=[])





            timeseries_source22.data = dict(
                time=[times[0], times[-1]],
                value=[values[0], values[-1]],
            )

            if freq_unit == "months":
                update_cycles(times, values)
            if freq_unit != "months":
                annual_cycle.visible = False
            if freq_unit == "months":
                annual_cycle.visible = True                        
            stats_div.text = f"""
            Area: ({xl:.2f}, {yl:.2f}) to ({xr:.2f}, {yu:.2f}) | Trend: {slope:.4f} per time step | P-value: {p_value:.4f}
            """
        else:
            # If no time dimension, just show the point value
            value = float(ts.values)
            stats_div.text = f"""
            Area: ({xl:.2f}, {yl:.2f}) to ({xr:.2f}, {yu:.2f}) | Value: {value:.2e}
            """

def update_cycles(times, values):
    df = pd.DataFrame({'value': values}, index=pd.DatetimeIndex(times))
    annual_means = df.groupby(df.index.month)['value'].mean()
    # Make sure annual_means is length 12 (fill missing months with np.nan)
    full_means = [annual_means.get(m, np.nan) for m in range(1, 13)]
    annual_source.data = dict(month=['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'], value=full_means)



def load_file():
    if not file_path.value.strip():
        stats_div.text = "Please enter a file path before loading."
        return
    try:


        # --- CLEAR ALL SOURCES ---
        timeseries_source.data = dict(time=[], value=[], filtered=[], trend=[], hidden=[])
        timeseries_source22.data = dict(time=[], value=[])
        atimeseries_source.data = dict(time=[], value=[], filtered=[], trend=[], hidden=[])
        atimeseries_source22.data = dict(time=[], value=[])
        annual_source.data = dict(month=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'], value=[0]*12)
        stats_div.text = ""
        results_div.text = "<b>Drag endpoints. Slope, OLS, Theil–Sen will show here.</b>"
        aresults_div.text = "<b>Drag endpoints. Slope, OLS, Theil–Sen will show here.</b>"
        # --- CLEAR ALL CONTROLS ---
        time_slider.value = 0
        time_slider.start = 0
        time_slider.end = 1
        time_select.value = []
        time_select.options = []
        # var_select.value = ""
        # var_select.options = []
        x_dim_select.value = ""
        x_dim_select.options = []
        y_dim_select.value = ""
        y_dim_select.options = []
        min_spinner.value = 0
        max_spinner.value = 1

        # # Optionally reset the dimension selector widget state:
        dim_selector.time_dim.value = "None"
        dim_selector.fourth_dim.value = "None"
        dim_selector.fifth_dim.value = "None"
        dim_selector.fourth_value.value = "None"
        dim_selector.fifth_value.value = "None"
        global dataset
        file_path.value = file_path.value.replace("file:///", "/")
        
        dataset = xr.open_dataset(file_path.value)
        for dim in ['latitude', 'lat', 'y']:
            if dim in dataset.dims:
                dataset = dataset.sortby(dim)
                break
        dataset = adjust_coordinates(dataset)
        
        # Update dataset info using StringIO
        buffer = io.StringIO()
        dataset.info(buf=buffer)
        dataset_info_div.text = (
    f"<pre style='color: silver; font-family: monospace;'>{buffer.getvalue()}</pre>"
    f"<br><b>Loaded file:</b> {file_path.value}"
)
        buffer.close()
        
        var_select.options = list(dataset.data_vars.keys())
        if var_select.options:
            var_select.value = var_select.options[0]
            
        # Update dimension selector
        dim_selector.update_dimensions(dataset, var_select.value)
        
        dims = list(dataset.sizes.keys())
        x_dim_select.options = dims
        y_dim_select.options = dims
        
        x_dim = next((d for d in dims if 'lon' in d.lower()), dims[0])
        y_dim = next((d for d in dims if 'lat' in d.lower()), dims[0])
        time_dim = next((d for d in dims if any(key in d.lower() for key in ['time', 'year', 'date','month','day','hour','minute','second','index'])), None)
        
        x_dim_select.value = x_dim
        y_dim_select.value = y_dim
        
        if time_dim:
            time_slider.end = len(dataset[time_dim]) - 1
            time_slider.value = 0
            time_slider.step = 1
            times = [str(t) for t in dataset[time_dim].values]
            time_select.options = times
            time_select.value = []
        
        # Set initial min/max values
        data = dataset[var_select.value]
        robust_min, robust_max = get_robust_min_max(data.values)
        min_spinner.value = robust_min
        max_spinner.value = robust_max
        min_spinner.step = (robust_max - robust_min) / 100
        max_spinner.step = (robust_max - robust_min) / 100
        update_plot(None, None, None)
        update_lat_profile()      # <-- Add here!

        stats_div.text = "File loaded successfully"
    except Exception as e:
        stats_div.text = f"Error loading file: {str(e)}"
        
    except Exception as e:
        stats_div.text = f"Error loading file: {str(e)}"

def ensure_datetime(val):
    """Robustly convert Bokeh/Pandas/millis float to Python datetime."""
    if isinstance(val, datetime.datetime):
        return val
    elif isinstance(val, (np.integer, int, float, np.floating)):
        # ms since epoch (Bokeh JS default)
        return pd.to_datetime(val, unit='ms').to_pydatetime()
    elif isinstance(val, np.datetime64):
        return pd.to_datetime(val).to_pydatetime()
    elif isinstance(val, str):
        return pd.to_datetime(val).to_pydatetime()
    else:
        raise ValueError(f"Cannot convert {val} to datetime")

def pretty_timedelta(dt1, dt0):
    """Return (value, unit) tuple for the time difference, including months."""
    delta = dt1 - dt0
    total_seconds = abs(delta.total_seconds())
    total_days = total_seconds / (24*3600)

    # Use relativedelta if you want more accurate month calculation
    try:
        from dateutil.relativedelta import relativedelta
        rel = relativedelta(dt1, dt0)
        n_months = abs(rel.years*12 + rel.months)
    except ImportError:
        n_months = abs(dt1.year - dt0.year) * 12 + abs(dt1.month - dt0.month)

    if total_days >= 730:
        return (total_days / 365.25, "years")
    elif n_months >= 2:
        return (n_months, "months")
    elif total_days >= 2:
        return (total_days, "days")
    elif total_seconds >= 3600:
        return (total_seconds / 3600, "hours")
    elif total_seconds >= 60:
        return (total_seconds / 60, "minutes")
    else:
        return (total_seconds, "seconds")
    
def closest_idx(target, arr):
    """Return index in arr whose value is closest to target."""
    target = ensure_datetime(target)
    arr = [ensure_datetime(xx) for xx in arr]
    return int(np.argmin([abs((xx - target).total_seconds()) for xx in arr]))

def detect_frequency(x):
    if len(x) < 2:
        return None
    dts = np.diff(sorted(pd.to_datetime(x)))
    # Median delta
    dt = dts[len(dts)//2]
    days = dt / np.timedelta64(1, "D")
    if abs(days - 365.25) < 20:
        return "years"
    elif 28 <= days <= 31:
        return "months"
    elif 0.5 < days < 2:
        return "days"
    elif days < 1/24:
        return "hours"
    elif days < 1/(24*60):
        return "minutes"
    else:
        return "seconds"

def fixed_timedelta(dt1, dt0, freq_unit):
    """Return (value, unit) tuple based on detected frequency."""
    delta = dt1 - dt0
    total_seconds = abs(delta.total_seconds())
    total_days = total_seconds / (24*3600)

    if freq_unit == "years":
        value = total_days / 365.25
        unit = "years"
    elif freq_unit == "months":
        value = (dt1.year - dt0.year) * 12 + (dt1.month - dt0.month)
        value = abs(value) + abs(dt1.day - dt0.day)/30.44
        unit = "months"
    elif freq_unit == "days":
        value = total_days
        unit = "days"
    elif freq_unit == "hours":
        value = total_seconds / 3600
        unit = "hours"
    elif freq_unit == "minutes":
        value = total_seconds / 60
        unit = "minutes"
    else:
        value = total_seconds
        unit = "seconds"
    return (value, unit)

def update_div_timeseries(attr, old, new):
    x = [ensure_datetime(i) for i in timeseries_source.data['time']]
    y = [float(i) for i in timeseries_source.data['value']]
    xs = [ensure_datetime(i) for i in timeseries_source22.data['time']]
    ys = [float(i) for i in timeseries_source22.data['value']]
    if len(xs) != 2 or len(ys) != 2:
        results_div.text = "<b>Drag endpoints. Slope, OLS, Theil–Sen will show here.</b>"
        return
    idx0 = closest_idx(xs[0], x)
    idx1 = closest_idx(xs[1], x)
    if idx0 == idx1 or not (0 <= idx0 < len(x) and 0 <= idx1 < len(x)):
        results_div.text = "<b>Select two <i>different</i> points within range.</b>"
        return
    lo, hi = sorted([idx0, idx1])
    x_sel = x[lo:hi+1]
    y_sel = np.array(y[lo:hi+1])
    mask = ~np.isnan(y_sel)
    y_sel = y_sel[mask]
    x_sel = np.array(x_sel)[mask]
    if len(x_sel) > 1:
        numeric_x = np.arange(len(x_sel))
        ols = linregress(numeric_x, y_sel).slope
        ols_pv = linregress(numeric_x, y_sel).pvalue
        theil = theilslopes(y_sel, numeric_x)[0]
    else:
        ols = np.nan
        theil = np.nan
        ols_pv = np.nan
    dt0, dt1 = x[idx0], x[idx1]
    freq_unit = detect_frequency(x)
    delta_val, delta_unit = fixed_timedelta(dt1, dt0, freq_unit)
    dy = y[idx1] - y[idx0]
    slope = dy / delta_val if delta_val != 0 else float('nan')
    slope_str = f"Slope = {slope:.2e} per {delta_unit[:-1]}" if delta_val != 0 else "Slope = ∞"
    results_div.text = (
        f"<b>x0 = {dt0.strftime('%Y-%m-%d %H:%M:%S')}, y0 = {y[idx0]:.2e}<br>"
        f"x1 = {dt1.strftime('%Y-%m-%d %H:%M:%S')}, y1 = {y[idx1]:.2e}<br>"
        f"Δx = {delta_val:.2e} {delta_unit}, Δy = {dy:.2e}, {slope_str}<br>"
        f"OLS Slope = {ols:.2e}, OLS p-value = {ols_pv:.2e}, Theil–Sen Slope = {theil:.2e}</b>"
    )

def update_div_anomaly(attr, old, new):
    x = [ensure_datetime(i) for i in atimeseries_source.data['time']]
    y = [float(i) for i in atimeseries_source.data['value']]
    xs = [ensure_datetime(i) for i in atimeseries_source22.data['time']]
    ys = [float(i) for i in atimeseries_source22.data['value']]
    if len(xs) != 2 or len(ys) != 2:
        aresults_div.text = "<b>Drag endpoints. Slope, OLS, Theil–Sen will show here.</b>"
        return
    idx0 = closest_idx(xs[0], x)
    idx1 = closest_idx(xs[1], x)
    if idx0 == idx1 or not (0 <= idx0 < len(x) and 0 <= idx1 < len(x)):
        aresults_div.text = "<b>Select two <i>different</i> points within range.</b>"
        return
    lo, hi = sorted([idx0, idx1])
    x_sel = x[lo:hi+1]
    y_sel = np.array(y[lo:hi+1])
    mask = ~np.isnan(y_sel)
    y_sel = y_sel[mask]
    x_sel = np.array(x_sel)[mask]
    if len(x_sel) > 1:
        numeric_x = np.arange(len(x_sel))
        ols = linregress(numeric_x, y_sel).slope
        ols_pv = linregress(numeric_x, y_sel).pvalue
        theil = theilslopes(y_sel, numeric_x)[0]
    else:
        ols = np.nan
        theil = np.nan
        ols_pv = np.nan
    dt0, dt1 = x[idx0], x[idx1]
    freq_unit = detect_frequency(x)
    delta_val, delta_unit = fixed_timedelta(dt1, dt0, freq_unit)
    dy = y[idx1] - y[idx0]
    slope = dy / delta_val if delta_val != 0 else float('nan')
    slope_str = f"Slope = {slope:.3f} per {delta_unit[:-1]}" if delta_val != 0 else "Slope = ∞"
    aresults_div.text = (
        f"<b>x0 = {dt0.strftime('%Y-%m-%d %H:%M:%S')}, y0 = {y[idx0]:.2e}<br>"
        f"x1 = {dt1.strftime('%Y-%m-%d %H:%M:%S')}, y1 = {y[idx1]:.2e}<br>"
        f"Δx = {delta_val:.2e} {delta_unit}, Δy = {dy:.2e}, {slope_str}<br>"
        f"OLS Slope = {ols:.2e}, OLS p-value = {ols_pv:.2e}, Theil–Sen Slope = {theil:.2e}</b>"
    )

# Compute weighted mean over 'lon' and 'time' (if they exist)
def compute_lat_profile(ds, var):
    da = ds[var]
    lat = da['lat'] if 'lat' in da.dims else da['latitude']
    # Use weights for area (cosine of latitude)
    weights = np.cos(np.deg2rad(lat))
    weights.name = "weights"
    dims = [d for d in ['lon', 'longitude', 'time'] if d in da.dims]
    return da.weighted(weights).mean(dims)

def update_lat_profile():
    global dataset, var_select, lat_profile_source
    try:
        data = dataset[var_select.value]

        # Find lat and lon names (allow both 'lat' or 'latitude', etc)
        lat_name = next((d for d in data.dims if d.lower() in ['lat', 'latitude']), None)
        lon_name = next((d for d in data.dims if d.lower() in ['lon', 'longitude']), None)
        time_name = next((d for d in data.dims if 'time' in d.lower()), None)

        if not lat_name or not lon_name:
            print("Latitudinal mean profile failed: no lat/lon in dims:", data.dims)
            lat_profile_source.data = dict(x=[], y=[])
            return

        # Weight by cosine of latitude (in degrees)
        lat_vals = data[lat_name].values
        weights = np.cos(np.deg2rad(lat_vals))

        # If time is present and slider is used, select that time slice
        if time_name and hasattr(time_slider, 'value'):
            # Protect against out-of-bounds index
            tlen = data[time_name].size
            tval = int(np.clip(time_slider.value, 0, tlen-1))
            data = data.isel({time_name: tval})

        # Compute mean over longitude
        axes = []
        if lon_name in data.dims:
            axes.append(lon_name)

        profile = data.weighted(xr.DataArray(weights, dims=lat_name)).mean(dim=axes, skipna=True)

        lat_profile_source.data = dict(x=profile.values, y=lat_vals)
    except Exception as e:
        print("Latitudinal mean profile failed:", e)
        lat_profile_source.data = dict(x=[], y=[])

def process_line_string(line_string):
    if isinstance(line_string, (LineString, MultiLineString)):
        if isinstance(line_string, LineString):
            lines = [line_string]
        else:
            lines = list(line_string.geoms)
        
        for line in lines:
            coords = np.array(line.coords)
            if len(coords) > 1:
                # Split at the dateline
                splits = np.where(np.abs(np.diff(coords[:, 0])) > 180)[0] + 1
                segments = np.split(coords, splits)
                
                for segment in segments:
                    if len(segment) > 1:
                        x, y = segment[:, 0], segment[:, 1]
                        heatmap.line(x, y, line_color='black', line_width=1, line_alpha=0.5)

def get_robust_min_max(data_array, pct_low=1, pct_high=99):
    values = np.array(data_array).flatten()
    if values.size == 0 or not np.issubdtype(values.dtype, np.floating):
        return 0, 1
    finite = np.isfinite(values)
    if not np.any(finite):
        return 0, 1
    values = values[finite]
    vmin = np.percentile(values, pct_low)
    vmax = np.percentile(values, pct_high)
    if not np.isfinite(vmin) or not np.isfinite(vmax) or vmin >= vmax:
        vmin, vmax = np.nanmin(values), np.nanmax(values)
        if vmin == vmax:
            vmin, vmax = vmin - 0.5, vmax + 0.5
    return float(vmin), float(vmax)

def safe_float(val, fallback):
    try:
        if val is None or (isinstance(val, str) and val.strip() == ""):
            return fallback
        return float(val)
    except Exception:
        return fallback

def update_color_mapper(low, high):
    color_mapper.low = low
    color_mapper.high = high
    color_bar.color_mapper = color_mapper
    source.trigger('data', source.data, source.data)  # Force redraw

def update_plot(attr, old, new):
    global dataset
    if dataset is None:
        return
    try:
        data = dataset[var_select.value]
        dims = list(data.dims)
        current_dims = dim_selector.get_selection()
        x_dim = x_dim_select.value if x_dim_select.value and x_dim_select.value != 'None' else dims[0]
        y_dim = y_dim_select.value if y_dim_select.value and y_dim_select.value != 'None' else dims[1 if len(dims)>1 else 0]

        # --------- Time dimension ---------
        time_dim = current_dims.get('time_dim', None)
        if time_dim and time_dim != 'None':
            if attr == 'value' and isinstance(new, list) and new:
                idx = dataset[time_dim].values.searchsorted(np.datetime64(new[-1]))
                time_slider.value = int(idx)
            data = data.isel({time_dim: int(time_slider.value)})
            date_time_display.text = f"{str(dataset[time_dim].values[int(time_slider.value)])}"
        else:
            date_time_display.text = "No time dimension"

        # --------- 4th/5th dims ---------
        if current_dims.get('fourth_dim', 'None') != 'None':
            data = safe_sel(data, current_dims['fourth_dim'], current_dims['fourth_value'])
        if current_dims.get('fifth_dim', 'None') != 'None':
            data = safe_sel(data, current_dims['fifth_dim'], current_dims['fifth_value'])

        # --------- x/y ---------
        x = data[x_dim].values
        y = data[y_dim].values
        values = data.values
        if values.ndim > 2:
            values = np.squeeze(values)
        values = values.reshape(len(y), len(x))
        # Compute heatmap statistics (ignoring NaN)
        valid_vals = values[np.isfinite(values)]
        if valid_vals.size == 0:
            vmin = vmax = vmean = float('nan')
        else:
            vmin = np.min(valid_vals)
            vmax = np.max(valid_vals)
            vmean = np.mean(valid_vals)


        # Compose display string
        stats_txt = f"""
            <b>Map Stats @ {date_time_display.text if 'date_time_display' in globals() else ''}:</b>
            min = {vmin:.4f}, max = {vmax:.4f}, mean = {vmean:.4f}
        """
        heatmap_stats_div.text = stats_txt

        # --------- Robust min/max ---------
        robust_min, robust_max = get_robust_min_max(values)

        # Always use the current spinner value, fallback to robust if blank/None
        minv = safe_float(min_spinner.value, robust_min)
        maxv = safe_float(max_spinner.value, robust_max)
        if minv >= maxv:
            maxv = minv + 1  # Guarantee range

        update_color_mapper(minv, maxv)
        color_mapper.palette = get_palette(colormap_select.value)
        color_bar.color_mapper = color_mapper

        source.data = {
            'image': [values],
            'x': [x[0]],
            'y': [y[0]],
            'dw': [x[-1] - x[0]],
            'dh': [y[-1] - y[0]]
        }
        update_lat_profile()

    except Exception as e:
        stats_div.text = f"Error updating plot: {str(e)}"
# Optional: Also reset spinner on variable change if you want (recommended for clarity):
def var_select_callback(attr, old, new):
    data = dataset[new]
    robust_min, robust_max = get_robust_min_max(data.values)
    min_spinner.value = robust_min
    max_spinner.value = robust_max
    update_plot(attr, old, new)
    update_lat_profile()  # <-- Add this!

var_select.on_change('value', var_select_callback)


# Create plots
color_mapper = LinearColorMapper(palette=Viridis256, low=0, high=1)

heatmap = figure(width=900, height=450, y_range=(-90, 90),x_range=(-180, 180),
                min_border_bottom=80, min_border_right=120,
                toolbar_location='below',background_fill_color="#2d2d2d",border_fill_color="#2d2d2d",
                tools='pan,box_zoom,wheel_zoom,reset,save',
                active_scroll='wheel_zoom',
                                   styles={
'margin-top': '-5px','margin-left': '10px','padding': '15px', 'border-radius': '10px','box-shadow': '0 4px 4px #06ffcd67','background-color': '#2d2d2d'
                   })


rrr=heatmap.image(image='image', x='x', y='y', dw='dw', dh='dh',
            source=source,
            color_mapper=color_mapper)
print('ia maher2')
color_bar = ColorBar(background_fill_color="#2d2d2d",
    color_mapper=color_mapper,
    ticker=BasicTicker(),
    label_standoff=12,
    border_line_color=None,
    location=(0,0)
)
heatmap.add_layout(color_bar, 'right')



heatmap.add_tools(TapTool())
# Add box selection rectangle
box_rect = heatmap.rect("x", "y", "width", "height",
                       color="color", alpha="alpha",
                       source=sourcebox)
box_tool = BoxSelectTool(renderers = [box_rect], persistent=True)
heatmap.add_tools(box_tool)

# Add click marker to heatmap with increased size and line width
heatmap.scatter('x', 'y', 
              size=20,
              marker='cross',
              color='red', 
              alpha=1.0,
              line_width=2, 
              source=click_marker_source)
tltl = """<i>lat:</i> <b>$y{0.2f}</b> <br> <i>lon:</i> <b>$x{0.2f}</b> <br> <i>value:</i> <b>@image{0.5f}</b>"""; heatmap.add_tools(HoverTool(tooltips=hovfun(tltl),attachment="above",show_arrow=False,renderers = [rrr])); 

# Add coastlines
from shapely.geometry import LineString, MultiLineString
try:
    coastlines = cfeature.NaturalEarthFeature('physical', 'coastline', '110m')
    for geom in coastlines.geometries():
        process_line_string(geom)
except Exception as _coastline_err:
    print(f"[aether] Skipping coastline overlay (no network): {_coastline_err}")

# ---------------- TIMESERIES PLOT (Tab 1) ----------------
timeseries = figure(
    width=850, height=350, min_border_bottom=60, min_border_right=60,
    x_axis_type="datetime", title="Time Series",background_fill_color="#2d2d2d",border_fill_color="#2d2d2d",
    tools="pan,wheel_zoom,box_zoom,reset,save", active_scroll='wheel_zoom',
    styles={
'margin-top': '10px','margin-left': '10px','padding': '15px', 'background-color': '#2d2d2d'
    }
)

main_line = timeseries.line('time', 'value', source=timeseries_source, color='pink', legend_label='Original', line_width=2)
main_sc = timeseries.scatter('time', 'value', size=7, color='pink', alpha=0.7, source=timeseries_source, legend_label='Original')
timeseries.line('time', 'filtered', source=timeseries_source, color='lime', legend_label='Filtered', line_width=4)
timeseries.line('time', 'trend', source=timeseries_source, color='deepskyblue', legend_label='Trend', line_width=6)
timeseries.legend.location = "top_left"
timeseries.legend.orientation = "horizontal"
timeseries.legend.click_policy = "hide"

tltl = """<i>time:</i> <b>@time{%Y-%m-%d %H:%M}</b> <br> <i>value:</i> <b>@value</b>"""
timeseries.add_tools(HoverTool(tooltips=hovfun(tltl), formatters={"@time": "datetime", "@hidden": cusj()}, point_policy="follow_mouse",line_policy="none",mode="vline",show_arrow=False, renderers=[main_sc]))

# ---- Trend line for user selection (Tab 1) ----
timeseries_source22 = ColumnDataSource(data=dict(time=[], value=[]))  # Must be unique for Tab 1!
trend_points = timeseries.scatter(x='time', y='value', size=10, fill_color='orange', line_color='black', source=timeseries_source22)
trend_line = timeseries.line(x='time', y='value', line_color='orange', line_width=3, source=timeseries_source22)
trend_points.visible = False
trend_line.visible = False
draw_tool = PointDrawTool(renderers=[trend_points], add=False)
timeseries.add_tools(draw_tool)
results_div = Div(
    text="<b>Interactive mode disabled. Click the toggle tool in toolbar to start analysis.</b>", 
    width=1100, styles={'color': 'black', 'background-color': 'lightgray', 'padding':'8px', 'border-radius':'8px'}
)

toggle_callback = CustomJS(
    args=dict(trend_points=trend_points, trend_line=trend_line, draw_tool=draw_tool, results_div=results_div, plot=timeseries),
    code="""
        const currently_visible = trend_points.visible;
        trend_points.visible = !currently_visible;
        trend_line.visible = !currently_visible;
        if (!currently_visible) {
            plot.toolbar.active_tap = draw_tool;
            results_div.text = "<b>Interactive mode enabled! Drag the red endpoints to analyze different segments.</b>";
        } else {
            plot.toolbar.active_tap = null;
            results_div.text = "<b>Interactive mode disabled. Click the toggle tool in toolbar to start analysis.</b>";
        }
    """
)
toggle_action = CustomAction(
    icon="data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjQiIGhlaWdodD0iMjQiIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KICA8cGF0aCBkPSJNNCAyMEwyMCA0IiBzdHJva2U9IiNmZjY2MDAiIHN0cm9rZS13aWR0aD0iMyIgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIi8+Cjwvc3ZnPgo=",
    description="Toggle Interactive Mode",
    callback=toggle_callback
)

timeseries.add_tools(toggle_action)
Span_height = Span(dimension="height", line_dash="dashed", line_width=2, line_color="#878787")
Crosshair_Tool = CrosshairTool(overlay=Span_height)
timeseries.add_tools(Crosshair_Tool)
# ---------------- ANOMALY TIMESERIES PLOT (Tab 2) ----------------
atimeseries = figure(
    width=850, height=350, min_border_bottom=60, min_border_right=60,
    x_axis_type="datetime", title="Time Series",background_fill_color="#2d2d2d",border_fill_color="#2d2d2d",
    tools="pan,wheel_zoom,box_zoom,reset,save", active_scroll='wheel_zoom',
    styles={
'margin-top': '10px','margin-left': '10px','padding': '15px', 'background-color': '#2d2d2d'
    }
)

atimeseries.line('time', 'value', source=atimeseries_source, color='pink', legend_label='Original', line_width=2)
main_sca = atimeseries.scatter('time', 'value', source=atimeseries_source, size=7, color='pink', legend_label='Original')
atimeseries.line('time', 'filtered', source=atimeseries_source, color='lime', legend_label='Filtered', line_width=4)
atimeseries.line('time', 'trend', source=atimeseries_source, color='deepskyblue', legend_label='Trend', line_width=6)
atimeseries.legend.location = "top_left"
atimeseries.legend.click_policy = "hide"
atimeseries.legend.orientation = "horizontal"

tltl = """<i>time:</i> <b>@time{%Y-%m-%d %H:%M}</b> <br> <i>value:</i> <b>@value</b>"""
atimeseries.add_tools(HoverTool(tooltips=hovfun(tltl), formatters={"@time": "datetime", "@hidden": cusj()}, mode="vline", point_policy="snap_to_data",line_policy="none",show_arrow=False, renderers=[main_sca]))

# ---- Trend line for user selection (Tab 2, ANOMALIES) ----
atimeseries_source22 = ColumnDataSource(data=dict(time=[], value=[]))  # Must be unique for Tab 2!
atrend_points = atimeseries.scatter(x='time', y='value', size=10, fill_color='orange', line_color='black', source=atimeseries_source22)
atrend_line = atimeseries.line(x='time', y='value', line_color='orange', line_width=3, source=atimeseries_source22)
atrend_points.visible = False
atrend_line.visible = False
adraw_tool = PointDrawTool(renderers=[atrend_points], add=False)
atimeseries.add_tools(adraw_tool)
aresults_div = Div(
    text="<b>Interactive mode disabled. Click the toggle tool in toolbar to start analysis.</b>", 
    width=1100, styles={'color': 'black', 'background-color': 'lightgray', 'padding':'8px', 'border-radius':'8px'}
)
atoggle_callback = CustomJS(
    args=dict(trend_points=atrend_points, trend_line=atrend_line, draw_tool=adraw_tool, results_div=aresults_div, plot=atimeseries),
    code="""
        const currently_visible = trend_points.visible;
        trend_points.visible = !currently_visible;
        trend_line.visible = !currently_visible;
        if (!currently_visible) {
            plot.toolbar.active_tap = draw_tool;
            results_div.text = "<b>Interactive mode enabled! Drag the red endpoints to analyze different segments.</b>";
        } else {
            plot.toolbar.active_tap = null;
            results_div.text = "<b>Interactive mode disabled. Click the toggle tool in toolbar to start analysis.</b>";
        }
    """
)
atoggle_action = CustomAction(
    icon="data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjQiIGhlaWdodD0iMjQiIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KICA8cGF0aCBkPSJNNCAyMEwyMCA0IiBzdHJva2U9IiNmZjY2MDAiIHN0cm9rZS13aWR0aD0iMyIgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIi8+Cjwvc3ZnPgo=",
    description="Toggle Interactive Mode",
    callback=atoggle_callback
)
atimeseries.add_tools(atoggle_action)
Span_height = Span(dimension="height", line_dash="dashed", line_width=2, line_color="#878787")
Crosshair_Tool = CrosshairTool(overlay=Span_height)
atimeseries.add_tools(Crosshair_Tool)


timeseries_source22.on_change('data', update_div_timeseries)
atimeseries_source22.on_change('data', update_div_anomaly)
min_spinner.on_change('value', minmax_spinner_callback)
max_spinner.on_change('value', minmax_spinner_callback)

# ---- Tabs Layout ----
tabs0 = Tabs(tabs=[
    TabPanel(child=column(timeseries, results_div), title="Timeseries"),
    TabPanel(child=column(atimeseries, aresults_div), title="Anomalies"),
], stylesheets=[tabs_style], styles={'width':'890px'},)

# Annual cycle plot
annual_cycle = figure(width=550, height=350,x_range = annual_source.data["month"],
                     min_border_right=60, title="Annual Cycle",background_fill_color="#2d2d2d",border_fill_color="#2d2d2d",
                     tools=["pan,wheel_zoom,save"],
                     styles={
'margin-top': '40px','margin-left': '10px','padding': '15px', 'border-radius': '10px','box-shadow': '0 4px 4px #06ffcd67','background-color': '#2d2d2d'
                     })

r1 = annual_cycle.vbar(x='month', top='value', width=0.9, source=annual_source,bottom=0,color='deepskyblue',border_radius=14, line_color='black', hover_fill_color='orange')

annual_cycle.xaxis.axis_label = 'Month'
annual_cycle.yaxis.axis_label = 'Value'
tltl = """<i>month:</i> <b>@month</b> <br> <i>value:</i> <b>@value</b>"""; annual_cycle.add_tools(HoverTool(tooltips=hovfun(tltl),show_arrow=False,renderers = [r1])); 



# Source for latitudinal profile
lat_profile_source = ColumnDataSource(data=dict(x=[], y=[]))

lat_profile_plot = figure(
    width=400, height=450,
    y_axis_label="Latitude (°)",
    x_axis_label="Mean Value",
    title="Latitudinal Mean Profile",
    background_fill_color="#2d2d2d",border_fill_color="#2d2d2d",
    min_border_bottom=60, min_border_right=80,
    styles={'margin-top': '35px','margin-left': '-40px','padding': '15px', 'border-radius': '10px','box-shadow': '0 4px 4px #06ffcd67','background-color': '#2d2d2d'},
)

lat_line = lat_profile_plot.line(
    x='x', y='y', source=lat_profile_source,
    line_color='deepskyblue', line_width=2,
)

tltl = """<i>lat:</i> <b>@y{0.00} °</b> <br> <i>value:</i> <b>@x{0.00000}</b>"""
lat_profile_plot.add_tools(HoverTool(tooltips=hovfun(tltl), formatters={ "@hidden": cusj()}, mode="hline",show_arrow=False, renderers=[lat_line]))



# Connect callbacks
load_button.on_click(load_file)
var_select.on_change('value', update_plot)
x_dim_select.on_change('value', update_plot)
y_dim_select.on_change('value', update_plot)
time_slider.on_change('value', update_plot)
time_select.on_change('value', update_plot)
play_button.on_click(animate)
colormap_select.on_change('value', update_plot)
heatmap.on_event('tap', update_timeseries)
window_spinner.on_change('value', spinner_callback)
order_spinner.on_change('value', spinner_callback)
trend_method.on_change('active', spinner_callback)
min_spinner.on_change('value', update_plot)
max_spinner.on_change('value', update_plot)
heatmap.on_event(events.SelectionGeometry, update_box_selection)
dim_selector.set_update_callback(lambda attr, old, new: update_plot(attr, old, new))



merged_div = Div(
    text="""
    <span style="display:block;color:deepskyblue;font-size:44px;font-weight:bold;">Aether</span>
    <span style="display:block;color:orange;font-size:18px;margin-top:-14px;">A fast NetCDF explorer</span>
    """,
    styles={'width': '180px', 'background-color': 'black', 'padding': '10px', 'border-radius': '10px'},
    stylesheets=[fancy_div_style],
)
text_area_input = TextAreaInput(value=" ", rows=18, cols=85, title="My notes:", stylesheets = [textarea_style])

# Create dataset info div
dataset_info_div = Div( text="No dataset loaded",width=720, styles={ 'color': 'silver', 'font-size': '14px', 'margin': '10px', 'padding': '15px', 'border-radius': '10px', 'box-shadow': '0 6px 10px rgba(197, 153, 10, 0.2)', 'background-color': 'black', 'max-height': '400px', 'overflow-y': 'auto' } )
date_time_display = Div(text="", width=420, height=30, styles = {"font-size": "20px", "font-family": "Consolas, 'Courier New', monospace", "color": "#00ffe0",})
about_div = Div( text=""" <div style="text-align:center; color:#00ffe0; font-size:1.07em; font-family:Consolas, monospace;"> Developed with <span style="color:#ff4c4c;">&#10084;&#65039;</span> by <a href="https://github.com/mixstam1821" target="_blank" style="color:#ffb031; font-weight:bold; text-decoration:none;"> mixstam1821 </a> </div> """, width=420, height=38, styles={"margin-top": "10px"} )

# Layout
controls = column(
    merged_div,
    file_path,
    load_button,var_select,    row(x_dim_select,
    y_dim_select),
    column(dim_selector.get_layout(),
),
    time_slider, 
    play_button,
    time_select,
    row(colormap_select,min_spinner, max_spinner,),
    row(window_spinner,
    order_spinner,column(Div(text = "", styles = {'height': '7px'}),trend_method)),about_div,
styles = {'background': 'linear-gradient(135deg, #262627 60%, #0a4431 100%)', 'box-shadow': '0 8px 36px hsla(152, 90%, 68%, 0.333)', 'border-radius': '18px', 'margin-left': '2px', 'margin-top': '10px', 'margin-bottom': '5px', 'width': '400px', 'height': '1000px', 'position': 'relative', 'z-index': '10','padding': '20px', 'overflow-y': 'auto'},
stylesheets=[gstyle]
)

layout = column(
    row(
        controls,
        column(
            row(
                column(
    heatmap_stats_div,
    heatmap,stats_div
),lat_profile_plot
            ),
            row(tabs0, column(Div(text="", height=18), annual_cycle),styles={'margin-top': '-60px'}),
            row(dataset_info_div,text_area_input),  # Add dataset info div here
            styles = {'margin-left':'20px', 'margin-top':'5px'}
        ),
    ),
   stylesheets=[gstyle],
)

curdoc().add_root(layout)
curdoc().title = "Aether: NetCDF Explorer"
