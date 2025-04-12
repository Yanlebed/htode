from flask import Flask, request, render_template_string

app = Flask(__name__)

GALLERY_HTML = """
<!DOCTYPE html>
<html lang="uk">
<head>
  <meta charset="UTF-8" />
  <title>Фотогалерея</title>
  <style>
    body {
      font-family: Arial, sans-serif;
      margin: 15px;
    }
    h2 {
      margin-bottom: 10px;
    }
    /* The images display at maximum width */
    .gallery-img {
      width: 100%;         /* Full width of container */
      max-width: 100%;     /* No overflow horizontally */
      margin-bottom: 20px;
      cursor: zoom-in;     /* Indicate clickable zoom */
    }
    /* The Modal (background overlay) */
    .modal {
      display: none;       /* Hidden by default */
      position: fixed;     /* Stay in place */
      z-index: 9999;       /* On top */
      left: 0;
      top: 0;
      width: 100%;
      height: 100%;
      overflow: auto;
      background-color: rgba(0,0,0,0.8); /* black w/ opacity */
    }
    /* Modal Image styling */
    .modal-content {
      display: block;
      margin: auto;
      max-width: 90%;
      max-height: 90%;
      box-shadow: 0 0 10px #000;
    }
    /* Close button (top-right) */
    .close {
      position: absolute;
      top: 30px;
      right: 45px;
      color: #fff;
      font-size: 40px;
      font-weight: bold;
      cursor: pointer;
    }
    .close:hover,
    .close:focus {
      color: #bbb;
      text-decoration: none;
    }
  </style>
</head>
<body>
  <h2>Фотогалерея</h2>
  <div id="gallery"></div>

  <!-- The Modal -->
  <div id="myModal" class="modal">
    <span class="close" id="closeBtn">&times;</span>
    <img class="modal-content" id="modalImg">
  </div>

  <script>
    const urlParams = new URLSearchParams(window.location.search);
    const imagesParam = urlParams.get("images"); // e.g. "https://...,https://..."
    const galleryDiv = document.getElementById("gallery");
    if (imagesParam) {
      const imgArray = imagesParam.split(",");
      imgArray.forEach(url => {
        const img = document.createElement("img");
        img.src = url.trim();
        img.className = "gallery-img";
        // On click => open modal
        img.onclick = function() {
          openModal(url.trim());
        };
        galleryDiv.appendChild(img);
      });
    } else {
      galleryDiv.textContent = "Немає зображень.";
    }

    // Modal logic
    const modal = document.getElementById("myModal");
    const modalImg = document.getElementById("modalImg");
    const closeBtn = document.getElementById("closeBtn");

    function openModal(imageUrl) {
      modal.style.display = "block";
      modalImg.src = imageUrl;
    }

    closeBtn.onclick = function() {
      modal.style.display = "none";
    };

    // Close the modal if user clicks outside the image
    window.onclick = function(event) {
      if (event.target === modal) {
        modal.style.display = "none";
      }
    }
  </script>
</body>
</html>
"""

PHONE_HTML = """
<!DOCTYPE html>
<html lang="uk">
<head>
  <meta charset="UTF-8">
  <title>Телефони</title>
  <style>
    body {
      background: #FFF;    /* White page background */
      color: #000;         /* Black default text */
      margin: 15px;
      font-family: Arial, sans-serif;
    }
    h2 {
      margin-bottom: 10px;
    }
    .phone-list {
      /* If you want to control max width of the entire content */
      max-width: 600px;
      margin: 0 auto;    /* Center horizontally */
    }
    /* Each phone link is a block with white background, black text */
    a.phone-link {
      display: block;
      background: #FFF;   /* White background for each link */
      color: #000;        /* Black text */
      text-decoration: none;
      font-size: 20px;    /* Adjust as needed */
      padding: 10px;
      border: 1px solid #AAA;
      border-radius: 4px;
      margin: 10px 0;
      width: 100%;
      box-sizing: border-box; /* So padding doesn't exceed width */
    }
    a.phone-link:hover {
      background: #f9f9f9; /* Slight hover effect */
    }
  </style>
</head>
<body>
  <h2>Телефони</h2>
  <div class="phone-list" id="phone-list"></div>
  <script>
    const urlParams = new URLSearchParams(window.location.search);
    const numbersParam = urlParams.get("numbers"); // e.g. "380999999999,380971234567"

    const phoneDiv = document.getElementById("phone-list");
    if (numbersParam) {
      const phoneArray = numbersParam.split(",");
      phoneArray.forEach(num => {
        const link = document.createElement("a");
        link.href = "tel:" + num.trim();   // Tapping opens dialer
        link.className = "phone-link";
        link.textContent = num.trim();
        phoneDiv.appendChild(link);
      });
    } else {
      phoneDiv.textContent = "Немає телефонів.";
    }
  </script>
</body>
</html>
"""


@app.route("/gallery")
def gallery_route():
    return render_template_string(GALLERY_HTML)


@app.route("/phones")
def phones_route():
    return render_template_string(PHONE_HTML)


if __name__ == "__main__":
    # For local dev
    app.run(host="0.0.0.0", port=8080, debug=True)
