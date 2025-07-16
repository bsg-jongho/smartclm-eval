import streamlit as st
import boto3
import json

# SageMaker 런타임 클라이언트 생성
sagemaker_runtime = boto3.client('sagemaker-runtime')

# Streamlit 앱 인터페이스 구성
st.title("SageMaker 모델과 연동된 Streamlit 앱")
user_input = st.text_input("모델에 전달할 값을 입력하세요:")

if st.button("예측 실행"):
    # SageMaker 엔드포인트 호출
    response = sagemaker_runtime.invoke_endpoint(
        EndpointName='YOUR_ENDPOINT_NAME', # 본인의 엔드포인트 이름으로 변경
        ContentType='application/json',
        Body=json.dumps({"instances": [user_input]}) # 모델 입력 형식에 맞게 데이터 구성
    )
    # 결과 파싱 및 출력
    result = json.loads(response['Body'].read().decode())
    st.write("모델 예측 결과:", result)