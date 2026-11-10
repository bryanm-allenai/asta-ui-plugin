import streamlit as st

import sys

sys.path.insert(1, "../fcm_codes")
sys.path.insert(1, "../app_components")
from fcm_codes.general_functions import *
from fcm_codes.fcm_class import FCM_numpy
from app_components.inference_parameters import *
from app_components.fcm_graph_component import *
from app_components.inference_tab_linguistic import *
from app_components.file_upload_linguistic import *
from app_components.design_manually_linguistic import *
from app_components.sidebar import *

# General Page Configurations
st.set_page_config(
    page_title="FCM Construction and Inference (linguistic)",
    page_icon="🛠",
    layout="wide",
    menu_items={
        "Get Help": None,  # todo insert the github link
        "Report a Bug": "mailto:[email removed]",
        "About": "This app was created by Dr. Theodoros Tziolas under the supervision of Prof. Elpiniki Papageorgiou. It aims to provide a usefull AI tool that utilizes Fuzzy Cognitive Maps and Deep Learning for decision making.",
    },
)


# st.title("FCM Linguistic Construction and Inference")
# st.header(
#     "Construct an FCM based on linguistic variables and fuzzy sets theory.",
#     divider="blue",
# )

st.markdown(
    "<h1 style='text-align: center; color: #4A90E2;'>FCM Linguistic Designer 💡</h1>",
    unsafe_allow_html=True,
)
st.markdown(
    "<h3 style='text-align: center; color: #666;'>Experimenting using linguistic variables and fuzzy sets theory for FCM Construction and inference!</h3><hr>",
    unsafe_allow_html=True,
)

tab_design, tab_inference = st.tabs(["Linguistic FCM Design", "Inference"])

matrix_exist = False

# Code for tab expert
with tab_design:
    st.subheader(
        "Construct the FCM and Fuzzy Sets Manually, Import Files, or Aggregate Knowledge from Multiple Experts.",
        divider="blue",
    )
    mode = st.radio(
        "Select the designing mode",
        ["Design Manually", "File Upload", "Knowledge Aggregation"],
        captions=[
            "Define concepts and linguistic causal relations from scratch.",
            "Import a weight matrix and Fuzzy Membership Functions via paired .csv and .json files.",
            "Aggregate knowledge from multiple experts using paired .csv and .json files.",
        ],
        horizontal=True,
    )
    if mode == "Design Manually":
        sidebar_help_design_linguistic()
        dic_final = fuzzy_sets()
        edited_matrix, exists = manual_tab_linguistic(dic_final)
        if exists:
            graph_boolean = st.toggle("Generate FCM graph", False)
            if graph_boolean:
                graph(edited_matrix, True)
            matrix_exist = True
            edited_matrix = defuzzification_single(edited_matrix, dic_final)
            st.caption("Defuzzified weight matrix")
            st.dataframe(edited_matrix)
            graph_boolean_defuz = st.toggle("Generate FCM graph (Defuzzified)", False)
            if graph_boolean_defuz:
                graph(edited_matrix, False)
            # file_name = st.text_input('Download as...', 'file1', max_chars=15)
            # st.download_button('Download matrix as csv', data= convert_df(edited_matrix), file_name=file_name + '.csv', mime="text/csv")
            # st.download_button('Download fuzzy mfs as json', data= convert_df(edited_matrix), file_name=file_name + '.json', mime="text/csv")

    elif mode == "File Upload":
        sidebar_help_design_with_upload_linguistic()
        edited_matrix, file, dic_final = matrix_upload()
        if edited_matrix is not None and dic_final is not None:
            print(edited_matrix)
            matrix_exist = True
            graph_boolean = st.toggle("Generate FCM graph", False)
            if graph_boolean:
                graph(edited_matrix, True)
            matrix_exist = True
            edited_matrix = defuzzification_single(edited_matrix, dic_final)
            st.caption("Defuzzified weight matrix")
            st.dataframe(edited_matrix)
            graph_boolean_defuz = st.toggle("Generate FCM graph (Defuzzified)", False)
            if graph_boolean_defuz:
                graph(edited_matrix, False)

    elif mode == "Knowledge Aggregation":
        sidebar_help_knowledge_aggregation()
        dic_uploads = matrices_upload()
        if dic_uploads is not None:
            dummy_df, stored_mfs = aggregation_info_display(dic_uploads)
            edited_matrix = defuzification_widgets(dummy_df, stored_mfs)
            matrix_exist = True
            graph_boolean = st.toggle("Generate FCM graph (Defuzzified)", False)
            if graph_boolean:
                graph(edited_matrix)


# Code for tab inference
with tab_inference:
    if matrix_exist:

        num_iter, equilibrium, rule_text, activation_text, l, b = inference_parameters()
        initial_vector = define_initial_values(edited_matrix, activation_text)
        if np.all(initial_vector == 0):
            st.write("Pass an initial state vector")
        else:
            button = st.button("Inference")
            fcm = FCM_numpy(
                initial_vector,
                edited_matrix,
                num_iter,
                equilibrium,
                activation_text,
                rule_text,
                l,
                b,
            )
            if button:
                inference = fcm.inference()
                placeholder = inference_results(inference)
                button_clear = st.button("Clear")
                if button_clear:
                    placeholder.empty()
    else:
        non_matrix_definition()

sidebar_logo()
