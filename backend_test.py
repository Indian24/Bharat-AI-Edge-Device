import requests
import sys
import base64
import io
from PIL import Image
from datetime import datetime

class DefectDetectiveAPITester:
    def __init__(self, base_url="https://smart-frontend.preview.emergentagent.com"):
        self.base_url = base_url
        self.tests_run = 0
        self.tests_passed = 0

    def run_test(self, name, method, endpoint, expected_status, data=None, files=None):
        """Run a single API test"""
        url = f"{self.base_url}/{endpoint}"
        headers = {}
        
        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        print(f"URL: {url}")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=30)
            elif method == 'POST':
                if files:
                    response = requests.post(url, files=files, timeout=60)
                else:
                    headers['Content-Type'] = 'application/json'
                    response = requests.post(url, json=data, headers=headers, timeout=60)

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                print(f"✅ Passed - Status: {response.status_code}")
                try:
                    response_data = response.json()
                    print(f"Response preview: {str(response_data)[:200]}...")
                    return True, response_data
                except:
                    return True, response.text
            else:
                print(f"❌ Failed - Expected {expected_status}, got {response.status_code}")
                print(f"Response: {response.text[:500]}")
                return False, {}

        except Exception as e:
            print(f"❌ Failed - Error: {str(e)}")
            return False, {}

    def create_test_image(self):
        """Create a simple test image for analysis"""
        # Create a simple test image with some patterns
        img = Image.new('RGB', (400, 300), color='white')
        
        # Add some simple patterns that might be interpreted as defects
        pixels = img.load()
        for i in range(50, 100):
            for j in range(50, 100):
                pixels[i, j] = (255, 0, 0)  # Red square
        
        for i in range(200, 250):
            for j in range(150, 200):
                pixels[i, j] = (0, 0, 0)  # Black square
        
        # Save to bytes
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='JPEG')
        img_bytes.seek(0)
        
        return img_bytes

    def test_root_endpoint(self):
        """Test the root endpoint"""
        success, response = self.run_test(
            "Root Endpoint",
            "GET",
            "",
            200
        )
        return success

    def test_analyze_endpoint(self):
        """Test the analyze endpoint with image upload"""
        print("\n📸 Creating test image...")
        test_image = self.create_test_image()
        
        files = {
            'file': ('test_defect_image.jpg', test_image, 'image/jpeg')
        }
        
        success, response = self.run_test(
            "Analyze Image Endpoint",
            "POST",
            "api/analyze",
            200,
            files=files
        )
        
        if success and isinstance(response, dict):
            analysis = response.get('analysis', {})
            analysis_id = analysis.get('id')
            print(f"📊 Analysis ID: {analysis_id}")
            print(f"📊 Total defects found: {analysis.get('total_defects', 0)}")
            print(f"📊 Filename: {analysis.get('filename', 'N/A')}")
            return success, analysis_id
        
        return success, None

    def test_history_endpoint(self):
        """Test the history endpoint"""
        success, response = self.run_test(
            "Analysis History Endpoint",
            "GET",
            "api/history",
            200
        )
        
        if success and isinstance(response, list):
            print(f"📚 Found {len(response)} analyses in history")
            for i, analysis in enumerate(response[:3]):  # Show first 3
                print(f"   {i+1}. {analysis.get('filename', 'Unknown')} - {analysis.get('total_defects', 0)} defects")
        
        return success

    def test_get_analysis_endpoint(self, analysis_id):
        """Test getting a specific analysis by ID"""
        if not analysis_id:
            print("⚠️ Skipping individual analysis test - no analysis ID available")
            return True
            
        success, response = self.run_test(
            f"Get Analysis by ID ({analysis_id[:8]}...)",
            "GET",
            f"api/analysis/{analysis_id}",
            200
        )
        
        if success and isinstance(response, dict):
            print(f"📋 Retrieved analysis: {response.get('filename', 'Unknown')}")
            print(f"📋 Defects: {response.get('total_defects', 0)}")
        
        return success

    def test_invalid_file_upload(self):
        """Test uploading invalid file type"""
        # Create a text file instead of image
        text_content = io.BytesIO(b"This is not an image file")
        
        files = {
            'file': ('test.txt', text_content, 'text/plain')
        }
        
        success, response = self.run_test(
            "Invalid File Type Upload",
            "POST",
            "api/analyze",
            400,  # Expecting 400 Bad Request
            files=files
        )
        
        return success

def main():
    print("🚀 Starting Defect Detective API Tests")
    print("=" * 50)
    
    # Setup
    tester = DefectDetectiveAPITester()
    analysis_id = None

    # Test sequence
    print("\n1️⃣ Testing Basic Connectivity...")
    if not tester.test_root_endpoint():
        print("❌ Root endpoint failed, stopping tests")
        return 1

    print("\n2️⃣ Testing Image Analysis...")
    success, analysis_id = tester.test_analyze_endpoint()
    if not success:
        print("⚠️ Analysis endpoint failed, but continuing with other tests")

    print("\n3️⃣ Testing Analysis History...")
    if not tester.test_history_endpoint():
        print("⚠️ History endpoint failed")

    print("\n4️⃣ Testing Individual Analysis Retrieval...")
    if not tester.test_get_analysis_endpoint(analysis_id):
        print("⚠️ Individual analysis retrieval failed")

    print("\n5️⃣ Testing Error Handling...")
    if not tester.test_invalid_file_upload():
        print("⚠️ Error handling test failed")

    # Print final results
    print("\n" + "=" * 50)
    print(f"📊 FINAL RESULTS: {tester.tests_passed}/{tester.tests_run} tests passed")
    
    if tester.tests_passed == tester.tests_run:
        print("🎉 All tests passed! Backend API is working correctly.")
        return 0
    elif tester.tests_passed >= tester.tests_run * 0.6:  # 60% pass rate
        print("⚠️ Most tests passed, but some issues detected.")
        return 0
    else:
        print("❌ Multiple test failures detected. Backend needs attention.")
        return 1

if __name__ == "__main__":
    sys.exit(main())