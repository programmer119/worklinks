# WorkLinks 지원 상태 로그인/서버 저장 배포 가이드

## 상태

- UI와 Node.js 상태 API 코드는 GitHub에 있으나 **상태 API가 서버에서 실행되고 있음을 의미하지는 않습니다.**
- WorkLinks UI는 GitHub Pages(`https://worklinks.suaveforge.com/startup-support/`)에 있고, API는 별도 HTTPS origin인 `https://api-worklinks.suaveforge.com`을 사용하도록 설정했습니다.
- 상태 API는 별도 프로세스이며 기존 `server/naver-cafe-proxy.mjs`를 변경하지 않습니다. Naver 프록시(18190)를 건드리지 않습니다.
- 로그인 기능은 계정이 서버에 설정되어야 활성화됩니다. **계정을 만들거나 비밀번호를 사용자에게 전달하는 것은 운영자가 직접 해야 합니다.** 저장소에 비밀번호/세션 키를 커밋하지 마세요.

## 서버에 필요한 환경

Node.js 20 이상. HTTPS 리버스 프록시 또는 Cloudflare Tunnel에서
`api-worklinks.suaveforge.com` → `http://127.0.0.1:18191` 라우팅.

1. 비밀번호 해시 생성: `node server/worklinks-state-api.mjs hash '길고_무작위인_비밀번호_12자이상'`.
2. 세션 키 생성: `openssl rand -hex 32`.
3. 다음 값을 **Git 저장소가 아닌 서버 전용 환경변수**로 설정합니다.

```text
WORKLINKS_STATE_PORT=18191
WORKLINKS_STATE_HOST=127.0.0.1
WORKLINKS_STATE_DATA_DIR=/home/worklinks/data/user-states
WORKLINKS_ALLOWED_ORIGINS=https://worklinks.suaveforge.com,https://programmer119.github.io
WORKLINKS_SESSION_SECRET=<32자 이상의 랜덤 문자열>
WORKLINKS_USERS_JSON={"계정ID":"scrypt$<salt>$<hash>"}
```

`WORKLINKS_USERS_JSON`은 비밀번호 원문이 아니라 1단계에서 출력된 해시를 넣습니다. 예시는 형식만 보여준 것이며 실제 값이 아닙니다. 쉘에서 `$`가 해석되지 않도록 보호하세요.

서비스 실행 예: `node server/worklinks-state-api.mjs`. systemd, Docker 등으로 프로세스 관리하며 로그와 접근 권한을 통제하세요.

## 기존 데이터 보호

1. **절대 삭제하면 안 되는 기존 브라우저 키**
   - `externaltools_startup_support_status_v1`
   - `worklinks_startup_support_hidden_v1`
   - `worklinks_startup_support_business_v1`
2. 기존의 `true` 기록은 첫 로그인 시 서버 기록과 OR 병합합니다. 서버에 이미 있는 `true`를 `false`로 바꾸지 않습니다.
3. 새 결과 키는 `worklinks_startup_support_outcomes_v1`입니다. 이전 지원완료 기록은 결과를 임의로 성공/실패 지정하지 않고 **심사중·미확정**으로 표시합니다.
4. 로그인 후 각 사용자의 브라우저 복사본은 `worklinks_account_state_v1:<계정ID>`에 저장됩니다.
5. 서버 파일은 사용자 ID를 SHA-256으로 만든 파일명으로 저장합니다. 원자적 파일 교체 전에 `.bak` 백업을 남깁니다.
6. 오프라인에서 변경했더라도 작업 큐에 남기며, 서버의 더 새로운 값과 충돌하면 사용자에게 선택을 요구합니다.
7. 롤백 시 페이지 코드는 이전 커밋으로 돌아갈 수 있으나 **기존 브라우저 키 및 서버 데이터 파일을 삭제하거나 빈 값으로 교체하지 마세요.** 먼저 파일과 브라우저 저장소를 백업하세요.

## 운영 반영 전 확인

- `node --test tests/worklinks-state.test.mjs` 테스트 통과.
- API HTTPS/Tunnel 라우팅과 CORS 확인.
- 실제 계정 로그인 → 체크 변경 → 새로고침 → 재로그인 → 다른 브라우저 재조회.
- 기존 브라우저에서 체크해둔 지원완료·숨김·사업자 항목이 로그인 후 그대로 존재하는지 비교.
- 충돌 테스트에서 옛 브라우저 값이 최신 서버 값을 자동으로 덮어쓰지 않는지 확인.
- 사용자별 데이터가 서로 섞이지 않는지 확인.
- 브라우저 저장소와 서버 저장 폴더 모두 **사전에 백업**한 뒤 운영 브랜치에 반영.

## 기능 API

- `GET /api/worklinks/session` : 현재 로그인 사용자
- `POST /api/worklinks/login` : 서버 설정 계정 로그인
- `POST /api/worklinks/logout` : 로그아웃
- `GET /api/worklinks/state` : 사용자별 상태 조회
- `POST /api/worklinks/state/bootstrap` : 브라우저의 과거 true 기록을 서버에 추가 병합
- `POST /api/worklinks/state/patch` : 사용자 변경 기록 저장(필드별 revision 검증 및 충돌 반환)

로그인/상태 변경은 허용된 웹 origin, 세션 쿠키, `X-Worklinks-Client` 헤더로 제한합니다. 모든 상태는 사용자별로 분리되며 공개 GitHub Pages 저장소에는 저장하지 않습니다.
