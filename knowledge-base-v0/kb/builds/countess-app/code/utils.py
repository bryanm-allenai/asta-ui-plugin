fileIterator = """
        let imageFiles = [];
        let currentImageIndex = 0;

        function handleFileSelection(event) {
            const files = Array.from(event.target.files).filter(function(f) {
                const name = f.name.toLowerCase();
                return name.endsWith('.jpg') || name.endsWith('.jpeg') ||
                       name.endsWith('.png') || name.endsWith('.bmp');
            });

            // Sort the image files using natural sorting (handles numbers correctly)
            files.sort(function(a, b) {
                return a.name.localeCompare(b.name, undefined, {
                    numeric: true,
                    sensitivity: 'base'
                });
            });

            imageFiles = files;

            if (imageFiles.length > 0) {
                Shiny.setInputValue('total_images', imageFiles.length);
                currentImageIndex = 0;
                loadCurrentImage();
                // No autoplay, wait for processing_done signal
            }
        }

        async function loadCurrentImage() {
            if (imageFiles.length === 0) return;

            const file = imageFiles[currentImageIndex];
            // 12MB = 12 * 1024 * 1024 bytes
            if (file.size > 12 * 1024 * 1024) {
                // Create a 1024x1024 black PNG as a base64 string
                const canvas = document.createElement('canvas');
                canvas.width = 1024;
                canvas.height = 1024;
                const ctx = canvas.getContext('2d');
                ctx.fillStyle = 'black';
                ctx.fillRect(0, 0, 1024, 1024);
                canvas.toBlob(function(blob) {
                    const reader = new FileReader();
                    reader.onload = function(e) {
                        const base64 = e.target.result.split(',')[1];
                        Shiny.setInputValue('current_image', base64);
                        Shiny.setInputValue('current_index', currentImageIndex);
                        Shiny.setInputValue('current_image_name', file.name);
                    };
                    reader.readAsDataURL(blob);
                }, 'image/png');
                return;
            }
            const reader = new FileReader();
            reader.onload = function(e) {
                const base64 = e.target.result.split(',')[1];
                Shiny.setInputValue('current_image', base64);
                Shiny.setInputValue('current_index', currentImageIndex);
                Shiny.setInputValue('current_image_name', file.name);
            };
            reader.readAsDataURL(file);
        }

        function nextImage() {
            if (currentImageIndex < imageFiles.length - 1) {
                currentImageIndex++;
                console.log(currentImageIndex);
                loadCurrentImage();
                console.log(currentImageIndex);
            } else {
                Shiny.setInputValue('show_completion', true);
            }
        }

        // MutationObserver to watch for processing_done changes
        function setupProcessingDoneObserver() {
            const target = document.getElementById('processing_done');
            if (!target) return;
            let lastValue = target.textContent;
            const observer = new MutationObserver(function(mutationsList) {
                for (const mutation of mutationsList) {
                    if (mutation.type === 'childList') {
                        const newValue = target.textContent;
                        if (newValue !== lastValue) {
                            lastValue = newValue;
                            // Only advance if not at last image
                            if (currentImageIndex < imageFiles.length - 1) {
                                nextImage();
                            }
                        }
                    }
                }
            });
            observer.observe(target, { childList: true });
        }

        // Wait for DOMContentLoaded to set up observer
        document.addEventListener('DOMContentLoaded', function() {
            setupProcessingDoneObserver();
        });
    """
