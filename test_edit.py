import requests

url = "http://127.0.0.1:8000/pdf/edit-text"
with open(r"C:\Users\nomin\Downloads\Presentacion digital fisica 4.pdf", "rb") as f:
    response = requests.post(url, files={"file": f}, data={
        "old_text": "Equipo 7:",
        "new_text": "Equipo 8:",
        "page_num": 0
    })
    print("Status:", response.status_code)
    if response.status_code == 200:
        with open("editado.pdf", "wb") as out:
            out.write(response.content)
        print("PDF guardado!")
    else:
        print("Error:", response.json())