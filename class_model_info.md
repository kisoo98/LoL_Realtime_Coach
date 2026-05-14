# 챔피언 분류 모델 정보 (Champion Classifier)

## 📋 개요
본 문서는 미니맵에서 크롭(Crop)된 챔피언 아이콘 이미지를 통해 어떤 챔피언인지 식별하는 모델 B (챔피언 초상화 분류기)에 대한 학습 과정 및 모델 정보를 설명합니다.

---

## 📊 1. 모델 개요

### 기본 사양
- **분류 목적**: 172개 챔피언 이름 분류 (Classification)
- **학습 스크립트**: `train_portrait_classifier.py`
- **입력 이미지 크기**: 96 × 96 (미니맵 크롭 아이콘 권장 크기)
- **출력 (클래스 수)**: 172 (챔피언 이름)
- **기본 모델 아키텍처**: YOLO26 Classification 모델 (기본값: `yolo26n-cls.pt`)

---

## 🛠️ 2. 기본 학습 파라미터 (Hyperparameters)

스크립트에 기본값으로 설정된 주요 파라미터입니다. 필요에 따라 명령행 인자(CLI args)로 변경할 수 있습니다.

- **Epochs**: 50
- **Image Size (imgsz)**: 96
- **Batch Size**: 64
- **Optimizer**: AdamW (학습률: 0.001, 모멘텀: 0.9, warmup_epochs: 3, weight_decay: 0.0005)
- **Early Stopping Patience**: 15

### Augmentation 설정 (YOLO 내부)
데이터 증강은 사전에 실행하는 `augment_portraits.py`에 의해 주로 수행되므로, YOLO 내부의 증강 파라미터는 비교적 보수적으로 설정되어 있습니다.
- **flip**: 좌우/상하 반전 금지 (fliplr=0.0, flipud=0.0) - 챔피언 아이콘의 비대칭성 고려
- **rotate**: 회전 금지 (degrees=0.0)
- **translate**: 0.05
- **scale**: 0.10
- **erasing**: 0.10 (약한 Random Erasing 적용)
- **mixup**: 0.0 (분류 경계 흐려짐 방지)

---

## 📈 3. 학습 성능 (Performance Metrics)

학습 완료 후 검증 데이터셋(Validation Set)에 대한 최종 성능 지표입니다.

### 전체 성능
| 지표 | 수치 | 설명 |
|------|------|------|
| **Top-1 Accuracy** | **1.0000** | 가장 높은 확률로 예측한 챔피언이 실제 정답과 일치하는 비율 |
| **Top-5 Accuracy** | **1.0000** | 예측한 상위 5개 확률의 챔피언 중 실제 정답이 포함되는 비율 |
| **Loss** | **0.00001** | 검증 데이터셋의 최종 손실값 |

---

## 🖼️ 4. 학습 결과 시각화

> [!NOTE]
> 아래 이미지들은 학습 시 생성된 `runs/classify/champion_classifier/` 폴더 내의 결과물입니다. 학습 완료 후 실제 이미지 URL로 교체해주세요.

### 학습 곡선 (Results)
학습이 진행됨에 따라 Loss는 감소하고 Accuracy가 꾸준히 상승하여 안정적으로 수렴하는 과정을 보여줍니다.

<img width="720" height="480" alt="{4BB0D0EA-57A0-4B6A-A8CD-D15E03D7DFD2}" src="https://github.com/user-attachments/assets/7c43fd4d-e930-47b8-baa5-2a241fc18829" />


### 혼동 행렬 (Confusion Matrix)
172개 챔피언 클래스 전체에 대한 예측 정확도와 헷갈리기 쉬운 챔피언 간의 오분류 경향을 나타냅니다.

<img width="720" height="480" alt="{4EACBCB7-618F-477E-A17C-3138221FD05F}" src="https://github.com/user-attachments/assets/b716ff14-993d-4bb9-b992-aec1a2c826f0" />


### 예측 결과 예시 (Validation Predictions)
검증 데이터셋의 크롭된 챔피언 아이콘에 대해 모델이 챔피언 이름을 예측한 결과 예시입니다.

<img width="720" height="480" alt="{983FA7AF-3252-43AE-A49D-B6E4E1868657}" src="https://github.com/user-attachments/assets/134e681d-da78-4fdd-952f-a271646ed15b" />


---

## 📁 5. 파일 및 저장 경로 정보

- **학습 데이터 위치**: `data/portraits/`
- **학습 결과 로그 및 메트릭**: `runs/classify/champion_classifier/`
- **학습 과정 로그 기록**: `logs/train_portrait.log`
- **최종 저장 가중치 파일**: `models/champion_classifier.pt`

---

## ⚠️ 6. 사용 및 실행 방법

이 스크립트는 아래와 같은 명령어로 실행할 수 있습니다 (가상환경 활성화 필요).

```bash
# 기본 학습 실행 (GPU 자동 인식)
python train_portrait_classifier.py

# CPU에서 테스트용으로 실행 (5 epochs 제한)
python train_portrait_classifier.py --device cpu --epochs 5

# 더 큰 모델 아키텍처를 로드하여 비교 학습 진행
python train_portrait_classifier.py --weights yolo26s-cls.pt
```

### 비고
이 분류기는 객체 위치를 찾는 탐지기(Detector)와는 별개로 작동합니다. YOLO 탐지기가 먼저 미니맵에서 챔피언 아이콘 위치를 탐지하면, 그 이미지를 96x96 사이즈로 크롭한 뒤 본 분류기를 통해 해당 아이콘이 172개의 챔피언 중 정확히 어느 챔피언인지 추론하게 됩니다.
