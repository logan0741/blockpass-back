CREATE TABLE ocr_documents (
  id INT AUTO_INCREMENT PRIMARY KEY,
  customer_profile_id INT NULL,
  business_profile_id INT NULL,
  image_png BLOB NOT NULL,
  ocr_result JSON NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'pending',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CHECK (OCTET_LENGTH(image_png) <= 65535),
  CHECK ((customer_profile_id IS NOT NULL) + (business_profile_id IS NOT NULL) = 1),
  FOREIGN KEY (customer_profile_id) REFERENCES customer_profiles(id),
  FOREIGN KEY (business_profile_id) REFERENCES business_profiles(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
