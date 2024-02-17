FROM python:3.9

RUN apt-get update && apt-get install -y libgl1-mesa-glx

COPY . .

RUN pip install -r requirements.txt

CMD ["python3", "camera.py"]
