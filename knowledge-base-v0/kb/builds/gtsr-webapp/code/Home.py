from pathlib import Path

import streamlit as st


WEBAPP_DIR = Path(__file__).resolve().parent


st.set_page_config(
    page_title="Xiao-Yan Li's Group",
    page_icon=":honeybee:",
    layout="centered",
    initial_sidebar_state="auto",
    menu_items={
        "Get help": "mailto:[email removed]",
        "Report a bug": "mailto:[email removed]",
        "About": """
            ### GUI for the model/tool/package/software developed by Xiao-Yan Li's group.

            **Group Website**: https://www.xiaoyanli-mace.com/                                                  
            **GitHub**: https://github.com/Xiao-Yan-Li-group

            Each page corresponds to a standalone software tool or program.
        """,
    },
)


def apply_nus_theme() -> None:
    st.markdown(
        """
        <style>
        :root {
            --nus-blue: #003d7c;
            --nus-orange: #ef7c00;
            --nus-yellow-bg: #fff9e8;
        }

        .stApp,
        [data-testid="stMain"] {
            background-color: var(--nus-yellow-bg);
        }

        [data-testid="stSidebar"] {
            background-color: var(--nus-blue);
            border-right: 4px solid var(--nus-orange);
        }

        [data-testid="stSidebar"] *,
        [data-testid="stSidebar"] a {
            color: #ffffff;
        }

        [data-testid="stSidebarNav"] a[aria-current="page"] {
            background-color: var(--nus-orange);
            color: #ffffff;
        }

        [data-testid="stSidebarNav"] a:hover {
            background-color: rgba(239, 124, 0, 0.35);
        }

        h1, h2, h3 {
            color: var(--nus-blue);
        }

        .stButton > button {
            background-color: var(--nus-blue);
            border-color: var(--nus-blue);
            color: #ffffff;
        }

        .stButton > button:hover {
            background-color: var(--nus-orange);
            border-color: var(--nus-orange);
            color: #ffffff;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def home_page() -> None:
    st.title(":computer: MACE Tools")
    st.write("Tools/Packages/Models Developed by Xiao-Yan Li's group.")


apply_nus_theme()
st.sidebar.image(str(WEBAPP_DIR / "imgs" / "mace_logo.png"))
st.sidebar.write("© 2026 Xiao-Yan Li Group. CC-BY-4.0 License.")

navigation = st.navigation(
    {
        "": [
            st.Page(home_page, title="Home", icon=":material/home:", default=True),
        ],
        "PM": [
            st.Page(
                WEBAPP_DIR / "pages" / "PM" / "0-GTsR.py",
                title="GTsR",
                icon=":material/science:",
            ),
        ],
    }
)
navigation.run()
