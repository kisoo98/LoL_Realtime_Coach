## 📋 개요
본 문서는 `yolo26l_train.ipynb` 노트북을 통해 학습된 YOLO26l 모델(`best.pt`)의 구성, 학습 과정 및 성능 지표를 설명합니다. 이 모델은 리그 오브 레전드(LoL) 미니맵에서 챔피언 아이콘 및 미니맵 영역을 탐지하기 위해 최적화되었습니다.

---

## 📊 1. 모델 개요

### 기본 사양
- **모델 아키텍처**: YOLOv8l (Ultralytics YOLO 8.4.48)
- **학습 데이터셋**: `dataset_260506` (1,364장)
- **클래스 수**: 3 (`minimap`, `ORDER`, `CHAOS`)
- **생성 일자**: 2026-05-06
- **학습 환경**: Google Colab (NVIDIA A100-SXM4-40GB, 40GB VRAM)

### 클래스 탐지 대상
| 클래스 ID | 클래스명 | 설명 |
|-----------|---------|------|
| 0 | minimap | 게임 화면 내 미니맵 영역 |
| 1 | ORDER | 아군(Blue Team) 챔피언 아이콘 |
| 2 | CHAOS | 적군(Red Team) 챔피언 아이콘 |

---

## 🛠️ 2. 학습 파라미터 (Hyperparameters)

모델 학습 시 사용된 주요 파라미터 설정값입니다.

- **Epochs**: 100
- **Image Size (imgsz)**: 640 × 640
- **Batch Size**: 16 (최초 32 설정 후 메모리 부족으로 자동 조정)
- **Optimizer**: AdamW (Learning Rate: 0.001429, Momentum: 0.9)
- **Augmentation**: Albumentations (Blur, MedianBlur, ToGray, CLAHE 등 적용)
- **Loss Function**: Box Loss, Class Loss, DFL Loss 사용

---

## 📈 3. 학습 성능 (Performance Metrics)

100 에포크 학습 후 검증 데이터셋(Validation Set)에 대한 최종 성능 지표입니다.

### 전체 성능
| 지표 | 수치 | 설명 |
|------|------|------|
| **mAP50** | **0.9940** | IoU 0.5 기준 평균 정밀도 (매우 높음) |
| **mAP50-95** | **0.9111** | IoU 0.5~0.95 기준 평균 정밀도 |
| **Precision** | **0.9882** | 정밀도 (탐지한 것 중 실제 정답 비율) |
| **Recall** | **0.9882** | 재현율 (실제 정답 중 탐지해낸 비율) |

### 클래스별 상세 성능 (mAP50)
- **minimap**: 0.995
- **ORDER**: 0.992
- **CHAOS**: 0.995

---

## 🖼️ 4. 학습 결과 시각화

> [!NOTE]
> 아래 이미지들은 학습 시 생성된 `runs/detect/yolov26l_custom_training/` 폴더 내의 결과물입니다.

### 학습 곡선 (Results)
학습이 진행됨에 따라 Loss는 감소하고 mAP는 꾸준히 상승하여 안정적으로 수렴하였습니다.

<img width="720" height="480" alt="{1010E424-9CAE-4643-A4A9-F04B79C295B6}" src="https://github.com/user-attachments/assets/67ac3d47-662b-4ea4-a1ba-c40d034346f9" />


### 혼동 행렬 (Confusion Matrix)
대부분의 객체를 정확하게 분류하고 있으며, 배경(Background)과의 오탐지율이 매우 낮습니다.

<img width="720" height="480" alt="{0CC54B83-6169-40B0-8CA8-8AB24296A296}" src="https://github.com/user-attachments/assets/8732bbe3-8886-460b-8561-bf700727c111" />


### 예측 결과 예시 (Validation Predictions)
검증 데이터셋에 대해 모델이 예측한 결과입니다. 챔피언 아이콘과 미니맵 영역을 정확하게 탐지하고 있습니다.

<img width="720" height="480" alt="{CEBA243A-FD0D-41E9-A086-796BC9A556B9}" src="https://github.com/user-attachments/assets/686c18e6-27f8-41f8-be1b-ad6919d5bf17" />


---

## 📁 모델 파일 정보

- **학습 결과 경로**: `/content/drive/MyDrive/yolo_runs/yolov26l_custom_training-5`
- **최종 모델 파일**: `models/best.pt` (약 53.0MB)
- **레이어 구성**: 190 layers, 24,748,053 parameters
- **연산량**: 86.1 GFLOPs
- **추론 속도**: 이미지당 약 2.8ms (A100 기준)

---

## ⚠️ 비고
- 본 모델은 YOLO26l 구조를 기반으로 하며, 실시간 코칭 시스템에 적합한 빠른 추론 속도와 높은 정확도를 보입니다.
- `ORDER` 클래스의 데이터 수가 상대적으로 많았음에도 불구하고, `CHAOS` 클래스에 대해서도 높은 성능을 유지하고 있습니다.
