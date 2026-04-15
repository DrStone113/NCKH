# HƯỚNG DẪN CÀI ĐẶT RASA TRÊN WINDOWS

## Vấn đề bạn đang gặp phải

Bạn đang dùng Python 3.13.4 (mặc định), nhưng RASA 3.6.0 chỉ hỗ trợ Python 3.8-3.10.

## Giải pháp: Sử dụng Python 3.10

Bạn đã có Python 3.10.9 trên máy! Chỉ cần dùng đúng cách.

### Bước 1: Tạo Virtual Environment với Python 3.10

```bash
# Di chuyển vào thư mục dự án
cd "D:\Download\NCKH-20260304T104614Z-1-001\NCKH\29-1-2026\MedicalBot"

# Tạo virtual environment với Python 3.10
py -3.10 -m venv venv

# Kích hoạt virtual environment
venv\Scripts\activate

# Bạn sẽ thấy (venv) xuất hiện ở đầu dòng lệnh
```

### Bước 2: Cài đặt RASA trong Virtual Environment

```bash
# Upgrade pip trước
python -m pip install --upgrade pip setuptools wheel

# Cài rasa-sdk (đã test thành công)
pip install rasa-sdk==3.6.0

# Cài PyYAML trước (tránh lỗi build)
pip install pyyaml==6.0

# Cài RASA
pip install rasa==3.6.0
```

### Nếu vẫn gặp lỗi PyYAML

Lỗi bạn gặp là do PyYAML 5.4.1 không build được trên Python 3.10 Windows. Giải pháp:

```bash
# Cài phiên bản PyYAML mới hơn trước
pip install pyyaml==6.0.1

# Sau đó cài RASA (sẽ dùng PyYAML đã cài)
pip install rasa==3.6.0 --no-deps
pip install -r requirements_rasa.txt
```

### Bước 3: Kiểm tra cài đặt

```bash
# Kiểm tra RASA
rasa --version

# Nên hiển thị: Rasa 3.6.0
```

## Giải pháp thay thế: Dùng RASA 3.5.x

Nếu RASA 3.6.0 vẫn không cài được, dùng phiên bản 3.5.x:

```bash
pip install rasa==3.5.17
pip install rasa-sdk==3.5.1
```

## Các lệnh quan trọng

### Kích hoạt virtual environment
```bash
# Mỗi lần mở terminal mới, chạy lệnh này
cd "D:\Download\NCKH-20260304T104614Z-1-001\NCKH\29-1-2026\MedicalBot"
venv\Scripts\activate
```

### Thoát virtual environment
```bash
deactivate
```

### Chạy lệnh với Python 3.10 (không dùng venv)
```bash
# Thay vì: python script.py
# Dùng: py -3.10 script.py

py -3.10 merge_domain.py
py -3.10 train_data_generator.py
```

## Tạo file requirements_rasa.txt

Nếu cần cài RASA với --no-deps, tạo file này:

```txt
absl-py<1.5,>=0.9
aio-pika<9.0.0,>=8.2.3
aiohttp<3.9,>=3.8
APScheduler<4.0.0,>=3.6
attrs<24.0,>=19.3
boto3<2.0.0,>=1.12
botocore<2.0.0,>=1.12
CacheControl<0.13.0,>=0.12.9
cloudpickle<2.3,>=1.2
colorama<0.5.0,>=0.4.4
colorclass<2.3,>=2.2
coloredlogs<16,>=10
colorhash<2.0.0,>=1.0.2
confluent-kafka<2.0.0,>=1.9.0
cryptography<42.0.0,>=3.4.4
dask<2022.3.0,>=2.30.0
fbmessenger<7.0.0,>=6.0.0
google-auth<3,>=1.6.3
h11<0.15,>=0.9
httpx<0.24.0,>=0.23.0
jmespath<2.0.0,>=0.10.0
joblib<1.3.0,>=0.15.1
jsonpickle<3.1,>=1.3
jsonschema<4.18,>=3.2
kafka-python<3.0,>=2.0
matplotlib<3.6,>=3.1
mattermostwrapper<3.0.0,>=2.2
networkx<2.7,>=2.4
numpy<1.23,>=1.19
oauth2client<5.0.0,>=4.1.3
packaging<24.0,>=20.0
pika<2.0.0,>=1.0.0
prompt-toolkit<3.1,>=2.0
protobuf<4.0.0,>=3.12
psycopg2-binary<3.0.0,>=2.8.2
pydot<2.0.0,>=1.4.1
pyjwt<3.0.0,>=2.0.0
pykwalify<1.9.0,>=1.7.0
pymongo<5.0.0,>=3.8
pyparsing<4.0.0,>=2.4.5
python-dateutil<3.0.0,>=2.8
python-engineio<5,>=4
python-socketio<6,>=5
pytz<2023.0,>=2019.1
questionary<2.0.0,>=1.5.1
redis<5.0.0,>=4.5.4
regex<2022.11,>=2020.6
requests<3.0,>=2.23
rocketchat-API<2.0.0,>=1.3.1
ruamel.yaml<0.18.0,>=0.16.5
sanic<22.0.0,>=21.12.0
Sanic-Cors<3.0.0,>=2.0.0
sanic-jwt<2.0.0,>=1.6.0
sanic-routing<1.0.0,>=0.7.0
scikit-learn<1.2,>=1.0
scipy<1.10,>=1.4.1
sentry-sdk<2.0.0,>=1.14.0
sklearn-crfsuite<0.4,>=0.3.6
slack-sdk<4.0.0,>=3.19.0
SQLAlchemy<1.5.0,>=1.4.0
structlog<24.0.0,>=23.1.0
tarsafe<0.0.5,>=0.0.3
tensorflow<2.12,>=2.11
tensorflow-hub<0.13.0,>=0.12.0
tensorflow-text<2.12,>=2.11
terminaltables<4.0.0,>=3.1.0
tqdm<5.0,>=4.31
twilio<8.0.0,>=6.26.0
typing-extensions<5.0.0,>=4.1.1
typing-utils<0.2.0,>=0.1.0
ujson<6.0,>=1.35
webexteamssdk<1.7.0,>=1.1.1
```

## Tóm tắt các bước

1. ✅ Tạo virtual environment: `py -3.10 -m venv venv`
2. ✅ Kích hoạt: `venv\Scripts\activate`
3. ✅ Upgrade pip: `python -m pip install --upgrade pip setuptools wheel`
4. ✅ Cài rasa-sdk: `pip install rasa-sdk==3.6.0` (đã thành công)
5. ⚠️ Cài PyYAML: `pip install pyyaml==6.0.1`
6. ⚠️ Cài RASA: `pip install rasa==3.6.0`

## Liên hệ hỗ trợ

Nếu vẫn gặp vấn đề, có thể:
1. Dùng RASA 3.5.17 thay vì 3.6.0
2. Cài đặt trên Linux/WSL2 (ổn định hơn Windows)
3. Dùng Docker image của RASA
