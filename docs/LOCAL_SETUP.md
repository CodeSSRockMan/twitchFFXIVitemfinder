# Local Setup Documentation for twitch14sourcebot

## 1. Prerequisites
- Docker & Docker Compose
- Bash
- (Optional) AWS CLI & Terraform for cloud deploy

## 2. Start Jenkins Locally
```bash
cd jenkins
chmod +x jenkins_setup.sh
./jenkins_setup.sh start
```
- Jenkins will be available at: http://localhost:8080
- The initial admin password will be printed in the terminal.

## 3. Jenkins Pipeline
- Configure a pipeline job in Jenkins using the following steps:
  1. Set up a Multibranch Pipeline or use a Jenkinsfile (see below for example).
  2. The pipeline will build a Docker container for the project and run the Ansible playbook.

## 4. Project Docker Container
- The project Dockerfile is in `project/Dockerfile`.
- To build and run manually:
```bash
cd project
cp ../requirements.txt .
docker build -t twitch14-app .
docker run -d --name twitch14-app -p 5000:5000 twitch14-app
```

## 5. Ansible Playbook
- The playbook is in `ansible/playbook.yml` and uses `ansible/vars.yml` for variables.
- To run manually (requires Ansible):
```bash
cd ansible
ansible-playbook -i "localhost," -c local playbook.yml
```

## 6. Copy Log Files
- Use the provided `utils/copythat.py` script:
```bash
python utils/copythat.py /path/to/source/logs /path/to/destination
```

## 7. Destroy Jenkins
```bash
cd jenkins
./jenkins_setup.sh destroy
```

## 8. Terraform (Cloud Deploy)
- Edit `terraform/variables.tf` with your values.
- Initialize and apply:
```bash
cd terraform
terraform init
terraform apply
```

---

## Example Jenkinsfile
```
pipeline {
  agent any
  stages {
    stage('Build App Container') {
      steps {
        sh 'docker build -t twitch14-app ./project'
      }
    }
    stage('Run Ansible') {
      steps {
        sh 'ansible-playbook -i "localhost," -c local ansible/playbook.yml'
      }
    }
  }
}
```

---

- Jenkins: http://localhost:8080
- App (if exposed): http://localhost:5000
- Cloud endpoints: See Terraform outputs after apply.

## FFXIV Data Pipeline

This repository now includes a documented pipeline for ingesting FFXIV CSV/EXD datamining outputs, normalizing them, building relationship indexes, and producing an optimized cache/database for application queries.

See the full pipeline documentation: [FFXIV Sheets Pipeline](docs/FFXIV_Pipeline.md)

