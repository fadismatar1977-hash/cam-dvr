package com.camdvr

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.recyclerview.widget.RecyclerView

class CameraAdapter(
    private val cameras: List<MainActivity.Camera>,
    private val onClick: (MainActivity.Camera) -> Unit,
) : RecyclerView.Adapter<CameraAdapter.ViewHolder>() {

    class ViewHolder(view: View) : RecyclerView.ViewHolder(view) {
        val name: TextView = view.findViewById(android.R.id.text1)
        val status: TextView = view.findViewById(android.R.id.text2)
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
        val view = LayoutInflater.from(parent.context)
            .inflate(android.R.layout.simple_list_item_2, parent, false)
        return ViewHolder(view)
    }

    override fun onBindViewHolder(holder: ViewHolder, position: Int) {
        val cam = cameras[position]
        holder.name.text = cam.name
        holder.status.text = if (cam.online) "● مباشر" else "● معطل"
        holder.status.setTextColor(
            if (cam.online) 0xFF00FF00.toInt() else 0xFFFF4444.toInt()
        )
        holder.itemView.setOnClickListener { onClick(cam) }
    }

    override fun getItemCount() = cameras.size
}
