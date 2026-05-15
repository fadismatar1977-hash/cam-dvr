package com.camdvr

import android.os.Bundle
import android.view.View
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import org.json.JSONArray
import java.io.BufferedReader
import java.io.InputStreamReader
import java.net.HttpURLConnection
import java.net.URL

class MainActivity : AppCompatActivity() {

    private lateinit var serverUrl: EditText
    private lateinit var connectBtn: Button
    private lateinit var statusText: TextView
    private lateinit var cameraList: RecyclerView
    private lateinit var streamView: WebView

    private var baseUrl = ""
    private var cameras = listOf<Camera>()

    data class Camera(val id: Int, val name: String, val online: Boolean)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        serverUrl = findViewById(R.id.server_url)
        connectBtn = findViewById(R.id.connect_btn)
        statusText = findViewById(R.id.status_text)
        cameraList = findViewById(R.id.camera_list)
        streamView = findViewById(R.id.stream_view)

        streamView.settings.javaScriptEnabled = true
        streamView.webViewClient = WebViewClient()

        connectBtn.setOnClickListener { connect() }
    }

    private fun connect() {
        val url = serverUrl.text.toString().trim()
        if (url.isEmpty()) {
            statusText.text = "أدخل رابط السيرفر"
            return
        }
        baseUrl = url.trimEnd('/')
        statusText.text = "جارٍ الاتصال..."
        fetchCameras()
    }

    private fun fetchCameras() {
        Thread {
            try {
                val conn = URL("$baseUrl/api/cameras").openConnection() as HttpURLConnection
                conn.connectTimeout = 5000
                conn.readTimeout = 5000
                val reader = BufferedReader(InputStreamReader(conn.inputStream))
                val text = reader.readText()
                reader.close()

                val arr = JSONArray(text)
                val list = mutableListOf<Camera>()
                for (i in 0 until arr.length()) {
                    val obj = arr.getJSONObject(i)
                    list.add(Camera(
                        id = obj.getInt("id"),
                        name = obj.getString("name"),
                        online = obj.getBoolean("online"),
                    ))
                }
                cameras = list

                runOnUiThread {
                    statusText.text = "✓ متصل - ${list.size} كاميرات"
                    showCameraList()
                }
            } catch (e: Exception) {
                runOnUiThread {
                    statusText.text = "✗ فشل: ${e.message}"
                    Toast.makeText(this, "فشل الاتصال", Toast.LENGTH_SHORT).show()
                }
            }
        }.start()
    }

    private fun showCameraList() {
        cameraList.visibility = View.VISIBLE
        streamView.visibility = View.GONE
        cameraList.layoutManager = LinearLayoutManager(this)
        cameraList.adapter = CameraAdapter(cameras) { cam ->
            viewStream(cam.id)
        }
    }

    private fun viewStream(camId: Int) {
        cameraList.visibility = View.GONE
        streamView.visibility = View.VISIBLE
        statusText.text = "مشاهدة الكاميرا $camId"
        streamView.loadUrl("$baseUrl/stream/$camId")
    }

    override fun onBackPressed() {
        if (streamView.visibility == View.VISIBLE) {
            showCameraList()
            return
        }
        super.onBackPressed()
    }
}
