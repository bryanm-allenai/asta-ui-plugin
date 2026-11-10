import streamlit as st
import io

st.set_page_config(
    page_title="FCM Learning",
    page_icon="🎓",
    layout="wide",
    menu_items={
        "Get Help": None,  # todo insert the github link
        "Report a Bug": "mailto:[email removed]",
        "About": "This app was created by Dr. Theodoros Tziolas under the supervision of Prof. Elpiniki Papageorgiou. It aims to provide a usefull AI tool that utilizes Fuzzy Cognitive Maps and Deep Learning for decision making.",
    },
)

### This session state variable indicates that a dataset has been uploaded
if "uploaded" not in st.session_state.keys():
    st.session_state.uploaded = False

### This session state variable indicates that a dataset has preprocessed and is ready for learning
if "initialized_preprocessing" not in st.session_state.keys():
    st.session_state.initialized_preprocessing = False

if "normalized" not in st.session_state.keys():
    st.session_state.normalized = False

### This session state df is used when data are normalized and we want to keep the original
if "non_norm_working_df" not in st.session_state.keys():
    st.session_state.non_norm_working_df = None

### This session state variable indicates that a training is completed
if "training_finished" not in st.session_state.keys():
    st.session_state.training_finished = False

if "input_df" not in st.session_state.keys():
    st.session_state.input_df = None

if "output_df" not in st.session_state.keys():
    st.session_state.output_df = None

### This session state variable indicates that the training shall start. It is being toggled in the learning tab
if "train" not in st.session_state.keys():
    st.session_state.train = False

### This is the session state variable where the trained model will be stored
if "model" not in st.session_state.keys():
    st.session_state.model = None


### importing app components
import sys

sys.path.insert(1, "../fcm_codes")
sys.path.insert(1, "../app_components")
from app_components.data_upload import *
from app_components.data_cleansing_tab import *
from app_components.visualization_tab import *
from app_components.data_transformation_tab import *
from app_components.data_norm_tab import *
from app_components.data_split_tab import *
from app_components.learning_tab import *
from app_components.sidebar import *
from app_components.warning_signs import *


# Page title
st.markdown(
    "<h1 style='text-align: center; color: #4A90E2;'>FCM Learning 🎓</h1>",
    unsafe_allow_html=True,
)
st.markdown(
    "<h3 style='text-align: center; color: #666;'>Data-based weight matrix optimization</h3><hr>",
    unsafe_allow_html=True,
)


data_tab, data_visual, preprocessing_tab, learning_tab = st.tabs(
    ["📂 Data Upload", "📈 Data Visualization", "⚙️ Data Preprocessing", "🧠 Learning"]
)


with data_tab:
    # Check if a dataset is ALREADY uploaded and stored in memory
    if st.session_state.get('uploaded', False):
        st.sidebar.success("A dataset is currently loaded in memory.")
        st.info("A dataset is actively loaded. If you want to upload a different dataset or start over, click the button below.")
        
        # 1. The Clear Button
        if st.button("🗑️ Clear Dataset & Start Over"):
            st.session_state.uploaded = False
            st.session_state.initialized_preprocessing = False
            st.session_state.normalized = False
            st.session_state.training_finished = False
            st.session_state.output_df = None
            st.session_state.input_df = None
            st.session_state.model = None
            st.session_state.train = False
            st.session_state.non_norm_working_df = None

            if "working_df" in st.session_state.keys():
                del st.session_state.working_df
            
            st.rerun() # Instantly refreshes the page, making the uploader reappear!

        # 2. Render the dataset parameter options
        modify_dataset()

    else:
        # No dataset is uploaded yet, OR the user just cleared it.
        # Show the uploader!
        csv = upload_widgets()
        
        # NOTE: When the user clicks "Import data", your `upload_callback` fires.
        # Callbacks automatically rerun the Streamlit script from top to bottom.
        # Upon that rerun, `uploaded` will be True, and the app will instantly 
        # jump to the top `if` statement, cleanly hiding this uploader!


sidebar_widgets_task()
sidebar_widgets_show_df()

with data_visual:
    if st.session_state.uploaded:
        plot_widgets()
    else:
        st.markdown(
            """
        👆 Use the **📂 Data Upload** tab to upload and import a dataset for learning.
        # ⛔ This tab will be accesible after data importing. 
        """
        )


with preprocessing_tab:
    if st.session_state.uploaded:
        st.info("Select a processing step from the tabs below.")

        tab_cleansing, tab_transf, tab_norm, tab_split = st.tabs(
            [
                "🧹️ Data Cleansing",
                "🔨 Data Transformation",
                "⚖️ Data Normalization",
                "✂️ Data Split",
            ]
        )

        with tab_cleansing:
            warning_signs()
            datacleansing_widgets()

        with tab_transf:
            warning_signs()
            transformation_widgets()

        with tab_norm:
            warning_signs()
            data_normalization()

        with tab_split:
            warning_signs()
            spliting_widgets()

        if st.session_state.changed:
            c_1, c_2, c_3 = st.columns(3)
            with c_3:
                st.write("")
                restore = st.button(
                    "Restore all changes",
                    key="restored_changes",
                    on_click=restore_df_changes_callback,
                    help="This button will discard all the applied preprocessing methods, returning back the raw imported data",
                )

    else:
        st.markdown(
            """
        👆 Use the **📂 Data Upload** tab to upload and import a dataset for learning.
        # ⛔ This tab will be accesible after data importing. 
        """
        )


with learning_tab:
    if st.session_state.initialized_preprocessing:
        warning_signs()
        learning_method_widgets()
        results_widgets()
    else:
        if not st.session_state.uploaded:
            st.markdown(
                """
            👆 Use the **📂 Data Upload** tab to upload and import a dataset for learning.
            # ⛔ This tab will be accesible after data importing. 
            """
            )
        else:
            st.markdown(
                """
            👆 Use the **⚙️ Data Preprocessing** tab to process data and to split input/output columns.
            # ⛔ This tab will be accesible after data splitting. 
            """
            )


sidebar_logo()
