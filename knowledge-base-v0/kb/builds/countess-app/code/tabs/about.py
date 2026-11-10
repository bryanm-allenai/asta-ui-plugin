from shiny import ui

def get_ui():
    """
    Returns the UI components for the About tab.

    Creates a navigation panel containing information about the Countess
    application, including its purpose and functionality.

    Returns:
        ui.nav_panel: A Shiny navigation panel containing the About tab UI
    """
    return ui.nav_panel(
        "About",
        ui.h3("About Countess"),
        ui.p("Countess is an application for automatically counting eggs in images using machine learning. Countess was developed for root-knot nematode quantification for plant breeding, but may be useful in other species as well."),
        ui.h3("Using Countess"),
        ui.p("Go to the Count Eggs tab and choose a folder of counting-slide images (.jpg, .jpeg, .png, or .bmp). Countess processes each image in turn, drawing a box around each object it classifies as an egg and showing a running annotated preview. When every image has been processed, use the Download button to export image_name/count pairs to a CSV file."),
    )
