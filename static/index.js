$(document).ready(function() {
    var canvas = document.getElementById("canvas");
    var ctx = canvas.getContext("2d");
    var isDrawing = false;
    var points = [];
    function drawPoint(x, y) {
        ctx.fillStyle = "white";
        ctx.fillRect(x * 10, y * 10, 10, 10);  // Scale coordinates by 10
    }
    function startDrawing(event) {
        isDrawing = true;
        var rect = canvas.getBoundingClientRect();
        var x = Math.floor((event.clientX - rect.left) / 10);  // Scale coordinates by 10
        var y = Math.floor((event.clientY - rect.top) / 10);  // Scale coordinates by 10
        points.push({ x: x, y: y });
        drawPoint(x, y);
    }
    function continueDrawing(event) {
        if (!isDrawing) return;
        var rect = canvas.getBoundingClientRect();
        var x = Math.floor((event.clientX - rect.left) / 10);  // Scale coordinates by 10
        var y = Math.floor((event.clientY - rect.top) / 10);  // Scale coordinates by 10
        var lastPoint = points[points.length - 1];
        var dx = Math.abs(x - lastPoint.x);
        var dy = Math.abs(y - lastPoint.y);
        var sx = (lastPoint.x < x) ? 1 : -1;
        var sy = (lastPoint.y < y) ? 1 : -1;
        var err = dx - dy;
        while (true) {
            drawPoint(lastPoint.x, lastPoint.y);
            if (lastPoint.x === x && lastPoint.y === y) break;
            var e2 = 2 * err;
            if (e2 > -dy) {
                err -= dy;
                lastPoint.x += sx;
            }
            if (e2 < dx) {
                err += dx;
                lastPoint.y += sy;
            }
        }
        points.push({ x: x, y: y });
        classifyDrawing();
    }
    function stopDrawing() {
        isDrawing = false;
    }
    function classifyDrawing() {
        $.ajax({
            url: "/classify",
            type: "POST",
            contentType: "application/json",
            data: JSON.stringify({ points: points }),
            success: function(response) {
                var predictedLabel = response.predicted_label;
                var imageData = response.image_data;
                $("#predicted-label").text("Predicted label: " + predictedLabel);
                var imageSrc = "data:image/png;base64," + btoa(imageData);
                $("#canvas-image").attr("src", imageSrc);
            },
            error: function() {
                $("#predicted-label").text("Error occurred while classifying the image.");
            }
        });
    }

    canvas.addEventListener("mousedown", startDrawing);
    canvas.addEventListener("mousemove", continueDrawing);
    canvas.addEventListener("mouseup", stopDrawing);
    canvas.addEventListener("mouseleave", stopDrawing);
});