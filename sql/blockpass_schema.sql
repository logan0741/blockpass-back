-- BlockPass core schema

CREATE TABLE IF NOT EXISTS users (
  user_id INT PRIMARY KEY AUTO_INCREMENT,
  id VARCHAR(255) NOT NULL UNIQUE,
  password_hash VARCHAR(255),
  name VARCHAR(255),
  role VARCHAR(50),
  wallet_address VARCHAR(255),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS business_profiles (
  id INT PRIMARY KEY AUTO_INCREMENT,
  user_id INT NOT NULL,
  business_name VARCHAR(255),
  registration_number VARCHAR(255),
  CONSTRAINT fk_business_user FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS customer_profiles (
  id INT PRIMARY KEY AUTO_INCREMENT,
  user_id INT NOT NULL,
  CONSTRAINT fk_customer_user FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS facilities (
  id INT PRIMARY KEY AUTO_INCREMENT,
  business_id INT NOT NULL,
  name VARCHAR(255),
  category VARCHAR(50),
  address VARCHAR(255),
  lat DECIMAL(10,6),
  lng DECIMAL(10,6),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_facility_business FOREIGN KEY (business_id) REFERENCES business_profiles(id)
);

CREATE TABLE IF NOT EXISTS passes (
  id INT PRIMARY KEY AUTO_INCREMENT,
  business_id INT NOT NULL,
  facility_id INT,
  title VARCHAR(255),
  price INT,
  duration_days INT,
  status VARCHAR(50),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_pass_business FOREIGN KEY (business_id) REFERENCES business_profiles(id),
  CONSTRAINT fk_pass_facility FOREIGN KEY (facility_id) REFERENCES facilities(id)
);

CREATE TABLE IF NOT EXISTS refund_policies (
  id INT PRIMARY KEY AUTO_INCREMENT,
  pass_id INT NOT NULL,
  name VARCHAR(255),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_refund_policy_pass FOREIGN KEY (pass_id) REFERENCES passes(id)
);

CREATE TABLE IF NOT EXISTS refund_policy_rules (
  id INT PRIMARY KEY AUTO_INCREMENT,
  refund_policy_id INT NOT NULL,
  usage_percent INT,
  refund_percent INT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_refund_rule_policy FOREIGN KEY (refund_policy_id) REFERENCES refund_policies(id)
);

CREATE TABLE IF NOT EXISTS orders (
  id INT PRIMARY KEY AUTO_INCREMENT,
  user_id INT NOT NULL,
  pass_id INT NOT NULL,
  amount INT,
  status VARCHAR(50),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_order_user FOREIGN KEY (user_id) REFERENCES users(user_id),
  CONSTRAINT fk_order_pass FOREIGN KEY (pass_id) REFERENCES passes(id)
);

CREATE TABLE IF NOT EXISTS subscriptions (
  id INT PRIMARY KEY AUTO_INCREMENT,
  user_id INT NOT NULL,
  pass_id INT NOT NULL,
  start_date DATE,
  end_date DATE,
  status VARCHAR(50),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_subscription_user FOREIGN KEY (user_id) REFERENCES users(user_id),
  CONSTRAINT fk_subscription_pass FOREIGN KEY (pass_id) REFERENCES passes(id)
);

CREATE TABLE IF NOT EXISTS blockchain_contracts (
  id INT PRIMARY KEY AUTO_INCREMENT,
  order_id INT NOT NULL,
  contract_address VARCHAR(255),
  chain VARCHAR(50),
  status VARCHAR(50),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_blockchain_order FOREIGN KEY (order_id) REFERENCES orders(id)
);

CREATE TABLE IF NOT EXISTS refunds (
  id INT PRIMARY KEY AUTO_INCREMENT,
  order_id INT NOT NULL,
  refund_amount INT,
  reason VARCHAR(255),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_refund_order FOREIGN KEY (order_id) REFERENCES orders(id)
);
