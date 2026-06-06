import requests

url = "http://127.0.0.1:8000/pdf/edit-text"
with open(r"C:\Users\nomin\Downloads\Presentacion digital fisica 4.pdf", "rb") as f:
    response = requests.post(
        url + "?old_text=FUERZA%20EN%20CARGAS&new_text=EDITADO&page_num=0",
        files={"file": f}
    )
    print("Status:", response.status_code)
    if response.status_code == 200:
        with open("editado.pdf", "wb") as out:
            out.write(response.content)
        print("PDF guardado!")
    else:
        print("Error:", response.json())