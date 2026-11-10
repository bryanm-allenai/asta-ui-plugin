from shiny import ui, render, reactive
import numpy as np
import matplotlib.pyplot as plt
import cv2
import pandas as pd
import base64
import asyncio
from io import BytesIO
import utils
import egg_counter

def get_ui():
    """
    Returns the UI components for the Count Eggs tab.

    Creates a navigation panel containing:
    - Image folder selection input (multi-file picker, automatable)
    - Image display area
    - Completion message area
    - Hidden processing done signal
    - Download button for results CSV

    Returns:
        ui.nav_panel: A Shiny navigation panel containing the Count Eggs tab UI
    """
    return ui.nav_panel(
        "Count Eggs",
        ui.tags.script(utils.fileIterator),
        ui.tags.input(
            id="dir_input",
            type="file",
            multiple=True,
            accept="image/*,.jpg,.jpeg,.png,.bmp",
            onchange="handleFileSelection(event)",
        ),
        ui.br(),
        ui.output_ui("image_display"),
        ui.output_ui("completion_message"),
        ui.output_ui("processing_done"),  # Hidden output for JS signaling
        ui.download_button("downloadResults", "Download .csv of counts")
    )

def register_server(input, output, session, counts, processed_image, processing_done_counter):
    """
    Registers all server-side logic for the Count Eggs tab.

    Sets up reactive effects and render functions for:
    - Processing images and counting eggs
    - Displaying processed images
    - Showing completion messages
    - Downloading results

    Args:
        input: Shiny input object containing user inputs
        output: Shiny output object for rendering UI elements
        session: Shiny session object for managing session state
        counts: Reactive value storing DataFrame of image names and egg counts
        processed_image: Reactive value storing base64-encoded processed image
        processing_done_counter: Reactive value used to signal when processing is complete
    """

    @reactive.effect
    async def process_current_image():
        """
        Processes the current image to count eggs.

        This reactive effect is triggered when a new image is loaded. It:
        1. Decodes the base64 image data
        2. Processes the image using the egg counter model
        3. Updates the counts DataFrame with the result
        4. Creates a visualization of the processed image
        5. Encodes the result as base64 for display
        6. Signals that processing is complete
        """
        if not input.current_image():
            processed_image.set(None)
            return

        current_index = input.current_index() + 1
        total_images = input.total_images()

        with ui.Progress(min=1, max=total_images) as p:
            p.set(current_index,
                  message=f"Processing image {current_index} of {total_images}",
                  detail="Analyzing image for egg counts...")

            # Convert base64 to image
            print("loading image")
            image_data = base64.b64decode(input.current_image())
            nparr = np.frombuffer(image_data, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

            # Process image with egg counter
            try:
                img_rgb, count = egg_counter.countImage(img_rgb)
                img_rgb = cv2.resize(img_rgb, (0,0), fx=0.25, fy=0.25)
            except:
                img_rgb, count = cv2.resize(img_rgb, (0,0), fx=0.25, fy=0.25), "error"

            with reactive.isolate():
                counts.set(pd.concat([counts.get(), pd.DataFrame({"image_name": [input.current_image_name()], "count": [count]})]))

            # Create figure for this image
            fig = plt.figure(figsize=(10, 8))
            plt.imshow(img_rgb)
            plt.axis('off')
            plt.title(input.current_image_name())

            # Convert figure to base64
            buf = BytesIO()
            fig.savefig(buf, format='png', bbox_inches='tight')
            plt.close(fig)
            buf.seek(0)
            img_str = base64.b64encode(buf.getvalue()).decode()

            processed_image.set(img_str)
            # Signal to frontend that processing is done
            with reactive.isolate():
                processing_done_counter.set(processing_done_counter.get() + 1)

    @output
    @render.ui
    def image_display():
        """
        Renders the processed image with egg counts.

        Displays either a placeholder message when no image is loaded,
        or the processed image with detected eggs highlighted.

        Returns:
            ui.p or ui.img: A paragraph with instructions or an image element
        """
        if processed_image.get() is None:
            return ui.p("Select a folder of images to begin analysis")
        return ui.img(src=f"data:image/png;base64,{processed_image.get()}")

    @output
    @render.ui
    def completion_message():
        """
        Displays a completion message when all images have been processed.

        Shows a green success message in a styled div when the show_completion
        input is True, indicating that all images in the directory have been
        processed.

        Returns:
            ui.div or None: A styled div with completion message, or None if not complete
        """
        if input.show_completion():
            return ui.div(
                ui.h3("Processing Complete!", style="color: green;"),
                ui.p("All images have been processed."),
                style="margin: 20px 0; padding: 20px; background-color: #f0f0f0; border-radius: 5px;"
            )
        return None

    @output
    @render.ui
    def processing_done():
        """
        Creates a hidden div that signals when image processing is complete.

        This hidden element is observed by JavaScript to automatically advance
        to the next image once processing is done. The counter value changes
        each time an image is processed, triggering the JavaScript observer.

        Returns:
            ui.div: A hidden div containing the processing done counter value
        """
        # Hidden div for JS to observe
        return ui.div(str(processing_done_counter.get()), id="processing_done", style="display:none;")

    @render.download(filename="counts.csv")
    async def downloadResults():
        """
        Generates and downloads a CSV file containing egg counts for all processed images.

        Creates a CSV file with columns for image_name and count, containing
        the results of all processed images. The file is automatically downloaded
        when the user clicks the download button.

        Yields:
            str: CSV-formatted string of the counts DataFrame
        """
        await asyncio.sleep(0.25)
        yield counts.get().to_csv(index=False)
